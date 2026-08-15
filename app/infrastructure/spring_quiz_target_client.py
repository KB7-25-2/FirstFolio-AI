import httpx

from app.domain.quiz import QuizGenerationTargets

_TARGETS_PATH = "/api/internal/quiz-generation-targets"


class SpringQuizTargetClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
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
