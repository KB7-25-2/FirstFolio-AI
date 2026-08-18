from collections.abc import Sequence
from uuid import UUID

import httpx

from app.domain.quiz import BeBatchResponse, QuizGenerationTargets

_TARGETS_PATH = "/api/internal/quiz-generation-targets"
_BATCHES_PATH = "/api/internal/quiz-questions/batches"


class SpringQuizApiClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float = 10.0,
        batch_timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._batch_timeout_seconds = batch_timeout_seconds
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"X-Internal-Token": internal_token},
            transport=transport,
        )

    def find_targets(self) -> QuizGenerationTargets:
        response = self._client.get(_TARGETS_PATH)
        response.raise_for_status()
        payload = response.json()
        return QuizGenerationTargets.model_validate(payload["data"])

    def send_batch(
        self,
        batch_id: UUID,
        items: Sequence[dict[str, object]],
    ) -> BeBatchResponse:
        response = self._client.post(
            _BATCHES_PATH,
            json={"batch_id": str(batch_id), "items": list(items)},
            timeout=self._batch_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return BeBatchResponse.model_validate(payload["data"])
