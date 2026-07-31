import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_use_default_search_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEARCH_TOP_K", raising=False)

    settings = Settings(_env_file=None)

    assert settings.search_top_k == 5


def test_load_search_top_k_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_TOP_K", "3")

    settings = Settings(_env_file=None)

    assert settings.search_top_k == 3


def test_reject_search_top_k_less_than_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_TOP_K", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_use_default_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.embedding_model == "text-embedding-3-small"


def test_load_embedding_model_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embedding-model")

    settings = Settings(_env_file=None)

    assert settings.embedding_model == "custom-embedding-model"
