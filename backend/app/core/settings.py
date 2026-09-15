from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="",
        extra="ignore",
    )

    app_environment: Literal["development", "test", "production"] = "development"
    app_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5199"])
    knowledge_index_dir: Path = BACKEND_ROOT / "data" / "index"
    knowledge_documents_dir: Path = BACKEND_ROOT / "data" / "documents"
    embedding_cache_dir: Path = BACKEND_ROOT / ".cache" / "models"
    embedding_model_id: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_local_files_only: bool = False
    embedding_dimension: int = Field(default=384, ge=1)
    embedding_cpu_threads: int = Field(default=1, ge=1, le=4)
    chunk_tokens: int = Field(default=384, ge=1)
    chunk_overlap: int = Field(default=64, ge=0)
    knowledge_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["cadreai.com", "cadre.ai", "portal.gocadre.ai"]
    )
    knowledge_max_file_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    knowledge_max_url_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    knowledge_url_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    knowledge_max_files: int = Field(default=10, ge=1, le=50)
    knowledge_max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    knowledge_max_request_bytes: int = Field(default=21 * 1024 * 1024, ge=1)
    knowledge_max_urls: int = Field(default=10, ge=1, le=50)
    knowledge_admin_password: SecretStr | None = None
    knowledge_session_secret: SecretStr | None = None
    knowledge_session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    knowledge_session_cookie: str = "cadre_knowledge_session"
    knowledge_cookie_secure: bool = True
    knowledge_login_attempts: int = Field(default=5, ge=1, le=100)
    knowledge_login_window_seconds: int = Field(default=300, ge=1, le=86400)
    chat_retrieval_top_k: int = Field(default=6, ge=1, le=20)
    chat_retrieval_max_per_source: int = Field(default=2, ge=1, le=10)
    chat_retrieval_min_score: float = Field(default=0.7, ge=-1, le=1)
    chat_provider: Literal["disabled", "openai", "openrouter"] = "disabled"
    chat_base_url: str = ""
    chat_api_key: SecretStr | None = None
    chat_model: str = ""
    chat_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    chat_max_output_tokens: int = Field(default=400, ge=1, le=4096)
    chat_temperature: float = Field(default=0.1, ge=0, le=1)
    chat_max_history_messages: int = Field(default=8, ge=0, le=20)
    chat_max_input_chars: int = Field(default=2000, ge=1, le=10_000)
    chat_max_history_chars: int = Field(default=6000, ge=0, le=40_000)
    chat_context_token_budget: int = Field(default=1800, ge=1, le=8000)
    chat_max_request_bytes: int = Field(default=32 * 1024, ge=1, le=1024 * 1024)
    chat_rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    chat_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    chat_provider_retries: int = Field(default=1, ge=0, le=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
