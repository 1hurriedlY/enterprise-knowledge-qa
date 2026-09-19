from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr, model_validator
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
    hybrid_search_enabled: bool = True
    hybrid_vector_weight: float = Field(default=0.60, ge=0, le=1)
    hybrid_bm25_weight: float = Field(default=0.40, ge=0, le=1)
    bm25_cache_ttl_seconds: float = Field(default=60.0, gt=0, le=3600)
    bm25_cache_max_users: int = Field(default=100, ge=1, le=10000)
    bm25_cache_max_chunks: int = Field(default=10000, ge=1, le=1000000)
    rerank_enabled: bool = False
    rerank_base_url: HttpUrl | None = None
    rerank_api_key: SecretStr | None = None
    rerank_model: str | None = None
    rerank_top_n: int = Field(default=5, ge=1, le=10)
    rerank_score_threshold: float = Field(default=0.30, ge=0, le=1)
    rerank_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    tool_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    llm_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    vector_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    external_max_retries: int = Field(default=2, ge=0, le=3)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=60, ge=1, le=100000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_fail_open: bool = False

    @model_validator(mode="after")
    def validate_search_configuration(self) -> "Settings":
        if self.rerank_enabled and not self.rerank_model:
            raise ValueError("RERANK_MODEL is required when RERANK_ENABLED=true")
        if self.hybrid_search_enabled and (
            self.hybrid_vector_weight + self.hybrid_bm25_weight <= 0
        ):
            raise ValueError("At least one hybrid search weight must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    # Required fields are populated by BaseSettings from the environment.
    return Settings()  # type: ignore[call-arg]
