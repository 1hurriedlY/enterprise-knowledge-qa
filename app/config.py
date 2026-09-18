from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str
    redis_url: str
    qdrant_url: HttpUrl
    qdrant_collection: str = "knowledge_chunks"
    llm_base_url: HttpUrl
    llm_api_key: SecretStr
    chat_model: str
    embedding_model: str
    embedding_dimension: int = Field(gt=0)
    upload_dir: Path = Path("data/uploads")
    demo_user_email: str = "demo@example.com"
    demo_api_key: SecretStr
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    retrieval_score_threshold: float = Field(default=0.30, ge=0, le=1)
    tool_timeout_seconds: float = Field(default=5.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    # Required fields are populated by BaseSettings from the environment.
    return Settings()  # type: ignore[call-arg]
