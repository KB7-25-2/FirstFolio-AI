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


def test_use_default_generation_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GENERATION_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.generation_model == "gpt-4o-mini"


def test_load_generation_model_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENERATION_MODEL", "custom-generation-model")

    settings = Settings(_env_file=None)

    assert settings.generation_model == "custom-generation-model"


def test_use_default_openai_request_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_MAX_RETRIES", raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_timeout_seconds == 30.0
    assert settings.openai_max_retries == 2


def test_load_openai_request_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45.5")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "3")

    settings = Settings(_env_file=None)

    assert settings.openai_timeout_seconds == 45.5
    assert settings.openai_max_retries == 3


@pytest.mark.parametrize(
    ("environment_name", "invalid_value"),
    [
        ("OPENAI_TIMEOUT_SECONDS", "0"),
        ("OPENAI_TIMEOUT_SECONDS", "-1"),
        ("OPENAI_MAX_RETRIES", "-1"),
    ],
)
def test_reject_invalid_openai_request_settings(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    invalid_value: str,
) -> None:
    monkeypatch.setenv(environment_name, invalid_value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_use_default_faiss_file_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAISS_INDEX_PATH", raising=False)
    monkeypatch.delenv("FAISS_MAPPING_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.faiss_index_path.as_posix() == (
        "data/local/evaluation/financial_textbook.faiss"
    )
    assert settings.faiss_mapping_path.as_posix() == (
        "data/local/evaluation/financial_textbook_mysql_chunk_keys.json"
    )


def test_load_faiss_file_paths_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAISS_INDEX_PATH", "/tmp/custom.faiss")
    monkeypatch.setenv("FAISS_MAPPING_PATH", "/tmp/custom-mapping.json")

    settings = Settings(_env_file=None)

    assert settings.faiss_index_path.as_posix() == "/tmp/custom.faiss"
    assert settings.faiss_mapping_path.as_posix() == "/tmp/custom-mapping.json"


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


def test_load_mysql_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYSQL_HOST", "mysql-test")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DATABASE", "firstfolio_ai_test")
    monkeypatch.setenv("MYSQL_USER", "test-user")
    monkeypatch.setenv("MYSQL_PASSWORD", "test-password")

    settings = Settings(_env_file=None)

    assert settings.mysql_host == "mysql-test"
    assert settings.mysql_port == 3307
    assert settings.mysql_database == "firstfolio_ai_test"
    assert settings.mysql_user == "test-user"
    assert settings.mysql_password.get_secret_value() == "test-password"


def test_hide_mysql_password_from_settings_representation() -> None:
    settings = Settings(
        mysql_password="secret-password",
        _env_file=None,
    )

    assert "secret-password" not in repr(settings)


def test_use_default_aws_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AWS_REGION", raising=False)

    settings = Settings(_env_file=None)

    assert settings.aws_region == "ap-northeast-2"


def test_load_aws_storage_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("S3_BUCKET_NAME", "test-rag-bucket")

    settings = Settings(_env_file=None)

    assert settings.aws_region == "us-west-2"
    assert settings.s3_bucket_name == "test-rag-bucket"


def test_exclude_aws_credentials_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AWS_ACCESS_KEY_ID",
        "test-access-key",
    )
    monkeypatch.setenv(
        "AWS_SECRET_ACCESS_KEY",
        "test-secret-key",
    )

    settings = Settings(_env_file=None)
    settings_representation = repr(settings)

    assert not hasattr(settings, "aws_access_key_id")
    assert not hasattr(settings, "aws_secret_access_key")
    assert "test-access-key" not in settings_representation
    assert "test-secret-key" not in settings_representation
