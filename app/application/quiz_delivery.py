from collections.abc import Callable, Iterator, Sequence
from uuid import UUID, uuid4

from app.application.quiz_export import QuizExportError, to_be_quiz_payload
from app.domain.quiz import BeBatchResponse, QuizBatchRecord
from app.infrastructure.spring_quiz_api_client import SpringQuizApiClient

_MAX_BATCH_SIZE = 100


def send_records_to_be(
    records: Sequence[QuizBatchRecord],
    client: SpringQuizApiClient,
    batch_id_factory: Callable[[], UUID] = uuid4,
) -> list[BeBatchResponse]:
    exportable_items: list[dict[str, object]] = []
    for record in records:
        try:
            payload = to_be_quiz_payload(record)
        except QuizExportError:
            continue
        exportable_items.append({"item_id": str(record.item_id), "quiz": payload})

    return [
        client.send_batch(batch_id_factory(), chunk)
        for chunk in _chunk(exportable_items, _MAX_BATCH_SIZE)
    ]


def _chunk(
    items: Sequence[dict[str, object]],
    size: int,
) -> Iterator[Sequence[dict[str, object]]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
