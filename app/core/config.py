from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_port: int = 8000
    search_top_k: int = Field(default=5, ge=1)
    bm25_weight: float = Field(default=0.7, ge=0, le=1)
    faiss_weight: float = Field(default=0.3, ge=0, le=1)
    embedding_model: str = "text-embedding-3-small"
    generation_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_max_retries: int = Field(default=2, ge=0)
    faiss_index_path: Path = Path("data/local/evaluation/financial_textbook.faiss")
    faiss_mapping_path: Path = Path(
        "data/local/evaluation/financial_textbook_mysql_chunk_keys.json"
    )
    mysql_host: str = "mysql"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = "firstfolio_ai"
    mysql_user: str = "firstfolio_ai"
    mysql_password: SecretStr = SecretStr("")
    aws_region: str = "ap-northeast-2"
    s3_bucket_name: str = ""
    spring_internal_base_url: str = "http://localhost:8080"
    spring_internal_token: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
