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
    app_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    knowledge_index_dir: Path = BACKEND_ROOT / "data" / "index"
    knowledge_documents_dir: Path = BACKEND_ROOT / "data" / "documents"
    embedding_cache_dir: Path = BACKEND_ROOT / ".cache" / "models"
    embedding_model_id: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_local_files_only: bool = False
    embedding_dimension: int = Field(default=384, ge=1)
    chunk_tokens: int = Field(default=384, ge=1)
    chunk_overlap: int = Field(default=64, ge=0)
    knowledge_allowed_hosts: list[str] = Field(default_factory=lambda: ["cadreai.com"])
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
