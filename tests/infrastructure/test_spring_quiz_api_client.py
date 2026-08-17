from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest

from app.domain.quiz import ChapterType
from app.infrastructure.spring_quiz_api_client import SpringQuizApiClient

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

_BATCH_ID = UUID("6ae92192-73dc-4e2e-b7af-4f81f5ab84fe")
_ITEM_ID = UUID("c33132f0-350f-4d2b-85a6-44f147d0de30")

_BATCH_RESPONSE_PAYLOAD = {
    "data": {
        "batch_id": str(_BATCH_ID),
        "total": 1,
        "accepted": 1,
        "rejected": 0,
        "items": [
            {
                "item_id": str(_ITEM_ID),
                "result": "ACCEPTED",
                "question_id": 1001,
                "status": "REVIEW",
            }
        ],
    }
}


def test_find_targets_parses_response_and_sends_internal_token() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json=_TARGETS_PAYLOAD)

    client = SpringQuizApiClient(
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

    client = SpringQuizApiClient(
        base_url="http://spring.local",
        internal_token="wrong-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.find_targets()


def test_send_batch_posts_items_and_parses_response() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json=_BATCH_RESPONSE_PAYLOAD)

    client = SpringQuizApiClient(
        base_url="http://spring.local",
        internal_token="test-token",
        transport=httpx.MockTransport(handler),
    )

    quiz_payload = {"item_id": str(_ITEM_ID), "quiz": {"usage_type": "SUB_CHAPTER"}}
    result = client.send_batch(_BATCH_ID, [quiz_payload])

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.path == "/api/internal/quiz-questions/batches"
    assert request.headers["x-internal-token"] == "test-token"

    assert result.batch_id == _BATCH_ID
    assert result.accepted == 1
    assert result.rejected == 0
    assert result.items[0].item_id == _ITEM_ID
    assert result.items[0].result == "ACCEPTED"
    assert result.items[0].question_id == 1001


def test_send_batch_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "INVALID_BATCH_REQUEST"}})

    client = SpringQuizApiClient(
        base_url="http://spring.local",
        internal_token="test-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.send_batch(_BATCH_ID, [])


def test_send_batch_uses_dedicated_longer_timeout() -> None:
    client = SpringQuizApiClient(
        base_url="http://spring.local",
        internal_token="test-token",
        timeout_seconds=10.0,
        batch_timeout_seconds=60.0,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_BATCH_RESPONSE_PAYLOAD)
        ),
    )
    client._client.post = Mock(wraps=client._client.post)

    client.send_batch(_BATCH_ID, [])

    _, call_kwargs = client._client.post.call_args
    assert call_kwargs["timeout"] == 60.0
