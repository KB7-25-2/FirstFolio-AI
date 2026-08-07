from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.ports.quiz_prompt_repository import QuizPromptRepository
from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.quiz_validation import normalize_quiz_prompt
from app.domain.quiz import (
    QuestionType,
    QuizBatchDuplicate,
    QuizBatchError,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchRequestItem,
    QuizBatchStatus,
    QuizBatchSummary,
)


@dataclass(frozen=True, slots=True)
class QuizBatchRun:
    records: tuple[QuizBatchRecord, ...]
    summary: QuizBatchSummary


class QuizBatchService:
    def __init__(
        self,
        generation_service: QuizGenerationService,
        id_factory: Callable[[], UUID] = uuid4,
        prompt_repository: QuizPromptRepository | None = None,
    ) -> None:
        self._generation_service = generation_service
        self._id_factory = id_factory
        self._prompt_repository = prompt_repository

    def generate(
        self,
        items: Sequence[QuizBatchRequestItem],
    ) -> QuizBatchRun:
        if not items:
            raise ValueError("배치 입력에는 하나 이상의 항목이 필요합니다.")

        batch_id = self._id_factory()
        records: list[QuizBatchRecord] = []
        successful_prompts: list[str] = (
            list(self._prompt_repository.find_all_prompts())
            if self._prompt_repository is not None
            else []
        )
        successful_items_by_prompt: dict[str, UUID] = {}

        for requested_item in items:
            for _ in range(requested_item.count):
                item_id = self._id_factory()
                item_input = QuizBatchItemInput(
                    question_type=requested_item.question_type.strip(),
                    topic=requested_item.topic.strip(),
                )
                record = self._generate_item(
                    batch_id=batch_id,
                    item_id=item_id,
                    item_input=item_input,
                    successful_prompts=successful_prompts,
                    successful_items_by_prompt=successful_items_by_prompt,
                )
                records.append(record)

                if record.status == QuizBatchStatus.SUCCEEDED:
                    if record.result is None:
                        raise RuntimeError("성공 항목에 생성 결과가 없습니다.")
                    prompt = record.result.quiz.prompt
                    successful_prompts.append(prompt)
                    successful_items_by_prompt[normalize_quiz_prompt(prompt)] = item_id

                    if self._prompt_repository is not None:
                        self._prompt_repository.save(
                            prompt=prompt,
                            question_type=item_input.question_type,
                            topic=item_input.topic,
                        )

        return QuizBatchRun(
            records=tuple(records),
            summary=_summarize(batch_id, records),
        )

    def _generate_item(
        self,
        *,
        batch_id: UUID,
        item_id: UUID,
        item_input: QuizBatchItemInput,
        successful_prompts: Sequence[str],
        successful_items_by_prompt: dict[str, UUID],
    ) -> QuizBatchRecord:
        try:
            question_type = QuestionType(item_input.question_type)
        except ValueError:
            return _failure_record(
                batch_id=batch_id,
                item_id=item_id,
                item_input=item_input,
                stage="input_validation",
                errors=["unsupported_question_type"],
                reason="지원하지 않는 문제 유형입니다.",
            )

        if not item_input.topic:
            return _failure_record(
                batch_id=batch_id,
                item_id=item_id,
                item_input=item_input,
                stage="input_validation",
                errors=["topic_required"],
                reason="문제 주제는 비어 있을 수 없습니다.",
            )

        try:
            result = self._generation_service.generate(
                question_type=question_type,
                topic=item_input.topic,
                existing_prompts=tuple(successful_prompts),
            )
        except QuizGenerationValidationError as error:
            duplicate_prompt = (
                error.quiz.prompt
                if "duplicate_prompt" in error.errors and error.quiz is not None
                else None
            )
            original_item_id = (
                successful_items_by_prompt.get(normalize_quiz_prompt(duplicate_prompt))
                if duplicate_prompt is not None
                else None
            )

            if duplicate_prompt is not None and original_item_id is not None:
                return QuizBatchRecord(
                    batch_id=batch_id,
                    item_id=item_id,
                    status=QuizBatchStatus.DUPLICATE,
                    input=item_input,
                    result=None,
                    error=QuizBatchError(
                        stage=error.stage,
                        errors=list(error.errors),
                        reason=(
                            "정규화한 질문이 같은 배치의 선행 성공 항목과 동일합니다."
                        ),
                        unsupported_claims=list(error.unsupported_claims),
                    ),
                    duplicate=QuizBatchDuplicate(
                        original_item_id=original_item_id,
                        prompt=duplicate_prompt,
                    ),
                )

            if duplicate_prompt is not None:
                return _failure_record(
                    batch_id=batch_id,
                    item_id=item_id,
                    item_input=item_input,
                    stage=error.stage,
                    errors=list(error.errors),
                    reason="이전에 생성된 질문과 동일하여 중복 처리되었습니다.",
                )

            return _failure_record(
                batch_id=batch_id,
                item_id=item_id,
                item_input=item_input,
                stage=error.stage,
                errors=list(error.errors),
                reason=error.reason or str(error),
                unsupported_claims=list(error.unsupported_claims),
            )
        except Exception:
            return _failure_record(
                batch_id=batch_id,
                item_id=item_id,
                item_input=item_input,
                stage="quiz_generation",
                errors=["quiz_generation_failed"],
                reason="퀴즈 생성 서비스 호출 중 오류가 발생했습니다.",
            )

        return QuizBatchRecord(
            batch_id=batch_id,
            item_id=item_id,
            status=QuizBatchStatus.SUCCEEDED,
            input=item_input,
            result=result,
            error=None,
            duplicate=None,
        )


def _failure_record(
    *,
    batch_id: UUID,
    item_id: UUID,
    item_input: QuizBatchItemInput,
    stage: str,
    errors: list[str],
    reason: str,
    unsupported_claims: list[str] | None = None,
) -> QuizBatchRecord:
    return QuizBatchRecord(
        batch_id=batch_id,
        item_id=item_id,
        status=QuizBatchStatus.FAILED,
        input=item_input,
        result=None,
        error=QuizBatchError(
            stage=stage,
            errors=errors,
            reason=reason,
            unsupported_claims=unsupported_claims or [],
        ),
        duplicate=None,
    )


def _summarize(
    batch_id: UUID,
    records: Sequence[QuizBatchRecord],
) -> QuizBatchSummary:
    return QuizBatchSummary(
        batch_id=batch_id,
        total=len(records),
        succeeded=sum(record.status == QuizBatchStatus.SUCCEEDED for record in records),
        failed=sum(record.status == QuizBatchStatus.FAILED for record in records),
        duplicates=sum(
            record.status == QuizBatchStatus.DUPLICATE for record in records
        ),
    )
