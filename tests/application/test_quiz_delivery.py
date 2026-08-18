import json
from itertools import count
from uuid import UUID, uuid4

import httpx

from app.application.quiz_delivery import send_records_to_be
from app.domain.quiz import (
    Quiz,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchStatus,
    QuizExecution,
    QuizGenerationResult,
    QuizSource,
    QuizValidation,
)
from app.infrastructure.spring_quiz_api_client import SpringQuizApiClient


def _succeeded_record(
    main_chapter_id: int | None = 2,
    sub_chapter_id: int | None = 17,
) -> QuizBatchRecord:
    quiz = Quiz.model_validate(
        {
            "usage_type": "SUB_CHAPTER",
            "question_type": "TRUE_FALSE",
            "prompt": "정기 예금은 약정 기간 동안 돈을 맡기는 금융상품이다.",
            "scenario_json": None,
            "options": [
                {"option_id": "O", "text": "O"},
                {"option_id": "X", "text": "X"},
            ],
            "correct_answer": {"option_id": "O"},
            "explanation": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
            "difficulty": "EASY",
            "citations": [{"chunk_key": "47:0", "evidence_text": "정기 예금은 ..."}],
        }
    )
    return QuizBatchRecord(
        batch_id=uuid4(),
        item_id=uuid4(),
        status=QuizBatchStatus.SUCCEEDED,
        input=QuizBatchItemInput(
            question_type="TRUE_FALSE",
            topic="예금과 적금의 차이",
            main_chapter_id=main_chapter_id,
            sub_chapter_id=sub_chapter_id,
        ),
        result=QuizGenerationResult(
            quiz=quiz,
            sources=[
                QuizSource(
                    document_id=1,
                    chunk_key="47:0",
                    title="문서",
                    heading=None,
                    source_url=None,
                    published_at=None,
                    evidence_text="정기 예금은 ...",
                )
            ],
            validation=QuizValidation(
                schema_valid=True,
                answer_valid=True,
                citation_valid=True,
                grounded=True,
                duplicate=False,
                errors=[],
            ),
            execution=QuizExecution(
                model="gpt-4o-mini", input_tokens=1, output_tokens=1, elapsed_ms=1
            ),
        ),
        error=None,
        duplicate=None,
    )


def _client_recording_requests(
    captured: list[httpx.Request],
) -> SpringQuizApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = json.loads(request.content)
        item_ids = [item["item_id"] for item in body["items"]]
        return httpx.Response(
            200,
            json={
                "data": {
                    "batch_id": body["batch_id"],
                    "total": len(item_ids),
                    "accepted": len(item_ids),
                    "rejected": 0,
                    "items": [
                        {
                            "item_id": item_id,
                            "result": "ACCEPTED",
                            "question_id": 1,
                            "status": "REVIEW",
                        }
                        for item_id in item_ids
                    ],
                }
            },
        )

    return SpringQuizApiClient(
        base_url="http://spring.local",
        internal_token="test-token",
        transport=httpx.MockTransport(handler),
    )


def test_send_records_to_be_sends_only_exportable_records() -> None:
    exportable = _succeeded_record()
    not_exportable = _succeeded_record(main_chapter_id=None, sub_chapter_id=None)

    captured: list[httpx.Request] = []
    client = _client_recording_requests(captured)

    responses = send_records_to_be([exportable, not_exportable], client)

    assert len(captured) == 1
    assert len(responses) == 1
    assert responses[0].accepted == 1


def test_send_records_to_be_splits_into_chunks_of_100() -> None:
    records = [_succeeded_record() for _ in range(150)]

    captured: list[httpx.Request] = []
    client = _client_recording_requests(captured)

    batch_id_numbers = count(1)
    responses = send_records_to_be(
        records,
        client,
        batch_id_factory=lambda: UUID(int=next(batch_id_numbers)),
    )

    assert len(captured) == 2
    assert len(responses) == 2
    assert responses[0].total == 100
    assert responses[1].total == 50
