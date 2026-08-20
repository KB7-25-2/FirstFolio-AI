from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.quiz_validation import normalize_quiz_prompt
from app.domain.chunk import DocumentChunk
from app.domain.quiz import (
    QuestionType,
    QuizBatchDuplicate,
    QuizBatchError,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchRequestItem,
    QuizBatchStatus,
    QuizBatchSummary,
    QuizGenerationTargets,
    UsageType,
)


def build_batch_items_from_targets(
    targets: QuizGenerationTargets,
    question_types: Sequence[QuestionType],
    count_per_type: int = 3,
) -> list[QuizBatchRequestItem]:
    items: list[QuizBatchRequestItem] = []
    for main_chapter in targets.main_chapters:
        for sub_chapter in main_chapter.sub_chapters:
            for question_type in question_types:
                items.append(
                    QuizBatchRequestItem(
                        question_type=question_type.value,
                        topic=sub_chapter.title,
                        count=count_per_type,
                        main_chapter_id=sub_chapter.main_chapter_id,
                        sub_chapter_id=sub_chapter.sub_chapter_id,
                    )
                )
    return items


def build_main_chapter_items_from_targets(
    targets: QuizGenerationTargets,
    count_per_chapter: int = 1,
) -> list[QuizBatchRequestItem]:
    """대단원별로 MAIN_CHAPTER 시나리오 문항 배치 아이템을 만든다.

    소단원이 아닌 대단원 자체를 topic으로 검색하므로 sub_chapter_id는
    비워둔다. 리트리벌은 topic 텍스트 기반 하이브리드 서치라 대단원
    제목만으로도 관련 청크를 찾을 수 있다.
    """
    items: list[QuizBatchRequestItem] = []
    for main_chapter in targets.main_chapters:
        items.append(
            QuizBatchRequestItem(
                question_type=QuestionType.SCENARIO.value,
                topic=main_chapter.title,
                count=count_per_chapter,
                main_chapter_id=main_chapter.main_chapter_id,
                sub_chapter_id=None,
                usage_type=UsageType.MAIN_CHAPTER,
            )
        )
    return items


def build_daily_general_items_from_targets(
    targets: QuizGenerationTargets,
    question_types: Sequence[QuestionType],
    count_per_type: int = 3,
) -> list[QuizBatchRequestItem]:
    """기존 활성 소단원 주제를 재사용해 DAILY_GENERAL 문항 배치 아이템을 만든다.

    소단원 문항과 topic·근거는 동일하게 뽑되, usage_type만 DAILY_GENERAL로
    태그해 일일 퀘스트 풀에 들어가게 한다. sub_chapter_id는 그대로 남겨
    DailyQuestQuestionSelector의 약점 매칭 정확도를 높인다.
    """
    items: list[QuizBatchRequestItem] = []
    for main_chapter in targets.main_chapters:
        for sub_chapter in main_chapter.sub_chapters:
            for question_type in question_types:
                items.append(
                    QuizBatchRequestItem(
                        question_type=question_type.value,
                        topic=sub_chapter.title,
                        count=count_per_type,
                        main_chapter_id=sub_chapter.main_chapter_id,
                        sub_chapter_id=sub_chapter.sub_chapter_id,
                        usage_type=UsageType.DAILY_GENERAL,
                    )
                )
    return items


def build_daily_news_items_from_targets(
    chunks: Sequence[DocumentChunk],
    count_per_article: int = 1,
) -> list[QuizBatchRequestItem]:
    """등록된 뉴스 청크를 기사 단위로 묶어 DAILY_NEWS 배치 아이템을 만든다.

    published_at이 있는 청크만 뉴스로 판별한다(TextbookChunker는 이 값을
    채우지 않는다). quest_date는 그 기사의 발행일을 그대로 쓴다.
    """
    articles: dict[str, DocumentChunk] = {}
    for chunk in chunks:
        if chunk.published_at is None:
            continue
        articles.setdefault(chunk.document_id, chunk)

    items: list[QuizBatchRequestItem] = []
    for article_chunk in articles.values():
        items.append(
            QuizBatchRequestItem(
                question_type=QuestionType.SCENARIO.value,
                topic=article_chunk.title,
                count=count_per_article,
                usage_type=UsageType.DAILY_NEWS,
                quest_date=article_chunk.published_at.date(),
            )
        )
    return items


@dataclass(frozen=True, slots=True)
class QuizBatchRun:
    records: tuple[QuizBatchRecord, ...]
    summary: QuizBatchSummary


class QuizBatchService:
    def __init__(
        self,
        generation_service: QuizGenerationService,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._generation_service = generation_service
        self._id_factory = id_factory

    def generate(
        self,
        items: Sequence[QuizBatchRequestItem],
    ) -> QuizBatchRun:
        if not items:
            raise ValueError("배치 입력에는 하나 이상의 항목이 필요합니다.")

        batch_id = self._id_factory()
        records: list[QuizBatchRecord] = []
        successful_prompts: list[str] = []
        successful_items_by_prompt: dict[str, UUID] = {}

        for requested_item in items:
            for _ in range(requested_item.count):
                item_id = self._id_factory()
                item_input = QuizBatchItemInput(
                    question_type=requested_item.question_type.strip(),
                    topic=requested_item.topic.strip(),
                    main_chapter_id=requested_item.main_chapter_id,
                    sub_chapter_id=requested_item.sub_chapter_id,
                    usage_type=requested_item.usage_type,
                    quest_date=requested_item.quest_date,
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
                usage_type=item_input.usage_type,
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
