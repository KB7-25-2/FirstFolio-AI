import httpx
import pytest

from app.domain.quiz import ChapterType
from app.infrastructure.spring_quiz_target_client import SpringQuizTargetClient

_TARGETS_PAYLOAD = {
    "data": {
        "main_chapters": [
            {
                "main_chapter_id": 2,
                "title": "예·적금",
                "chapter_type": "ASSET",
                "sub_chapters": [
                    {
                        "sub_chapter_id": 17,
                        "main_chapter_id": 2,
                        "title": "예금과 적금의 차이",
                    }
                ],
            }
        ]
    }
}


def test_find_targets_parses_response_and_sends_internal_token() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json=_TARGETS_PAYLOAD)

    client = SpringQuizTargetClient(
        base_url="http://spring.local",
        internal_token="test-token",
        transport=httpx.MockTransport(handler),
    )

    targets = client.find_targets()

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.path == "/api/internal/quiz-generation-targets"
    assert request.headers["x-internal-token"] == "test-token"

    assert len(targets.main_chapters) == 1
    main_chapter = targets.main_chapters[0]
    assert main_chapter.main_chapter_id == 2
    assert main_chapter.chapter_type == ChapterType.ASSET
    assert len(main_chapter.sub_chapters) == 1
    assert main_chapter.sub_chapters[0].sub_chapter_id == 17
    assert main_chapter.sub_chapters[0].main_chapter_id == 2


def test_find_targets_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "INTERNAL_CALL_REQUIRED"}})

    client = SpringQuizTargetClient(
        base_url="http://spring.local",
        internal_token="wrong-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.find_targets()
