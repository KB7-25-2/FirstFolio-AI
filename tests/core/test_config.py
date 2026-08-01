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


def test_use_default_hybrid_search_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BM25_WEIGHT", raising=False)
    monkeypatch.delenv("FAISS_WEIGHT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.bm25_weight == 0.7
    assert settings.faiss_weight == 0.3


def test_load_hybrid_search_weights_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BM25_WEIGHT", "0.6")
    monkeypatch.setenv("FAISS_WEIGHT", "0.4")

    settings = Settings(_env_file=None)

    assert settings.bm25_weight == 0.6
    assert settings.faiss_weight == 0.4


@pytest.mark.parametrize(
    ("environment_name", "invalid_value"),
    [
        ("BM25_WEIGHT", "-0.1"),
        ("BM25_WEIGHT", "1.1"),
        ("FAISS_WEIGHT", "-0.1"),
        ("FAISS_WEIGHT", "1.1"),
    ],
)
def test_reject_hybrid_search_weight_outside_allowed_range(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    invalid_value: str,
) -> None:
    monkeypatch.setenv(
        environment_name,
        invalid_value,
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
