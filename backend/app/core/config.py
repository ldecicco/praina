from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project Tracker API"
    environment: str = "dev"
    api_v1_prefix: str = "/api/v1"
    root_path: str = ""
    registration_enabled: bool = True
    app_host: str | None = None
    app_port: int | None = None
    postgres_host: str | None = None
    postgres_port: int | None = None
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    database_url: str | None = None
    cors_allowed_origins: str | None = None
    frontend_app_url: str = "http://localhost:5173"
    documents_storage_path: str = "storage/documents"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen3.5:9b", validation_alias="OLLAMA_MODEL")
    ollama_enable_thinking: bool = Field(default=False, validation_alias="OLLAMA_ENABLE_THINKING")
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe", validation_alias="OLLAMA_EMBEDDING_MODEL")
    text_inference_provider: str = Field(default="ollama", validation_alias="TEXT_INFERENCE_PROVIDER")
    codex_model: str = Field(default="gpt-5.4", validation_alias="CODEX_MODEL")
    codex_timeout_seconds: int = Field(default=120, validation_alias="CODEX_TIMEOUT_SECONDS")
    embedding_dimension: int = Field(default=768, validation_alias="EMBEDDING_DIMENSION")
    embedding_batch_size: int = Field(default=16, validation_alias="EMBEDDING_BATCH_SIZE")
    embedding_http_timeout_seconds: int = Field(default=300, validation_alias="EMBEDDING_HTTP_TIMEOUT_SECONDS")
    assistant_temperature: float = 0.2
    assistant_http_timeout_seconds: int = 60
    action_extraction_http_timeout_seconds: int = 180
    call_extraction_http_timeout_seconds: int = Field(default=900, validation_alias="CALL_EXTRACTION_HTTP_TIMEOUT_SECONDS")
    call_qa_http_timeout_seconds: int = Field(default=600, validation_alias="CALL_QA_HTTP_TIMEOUT_SECONDS")
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str | None = None
    calendar_sync_past_days: int = 14
    calendar_sync_future_days: int = 90
    log_level: str = "INFO"
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_USERNAME")
    telegram_webhook_secret: str | None = Field(default=None, validation_alias="TELEGRAM_WEBHOOK_SECRET")
    firebase_credentials_path: str | None = Field(default=None, validation_alias="FIREBASE_CREDENTIALS_PATH")
    firebase_project_id: str | None = Field(default=None, validation_alias="FIREBASE_PROJECT_ID")

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        provider = (self.text_inference_provider or "").strip().lower()
        if provider not in {"ollama", "codex"}:
            raise ValueError("TEXT_INFERENCE_PROVIDER must be either 'ollama' or 'codex'.")
        self.text_inference_provider = provider
        if not self.database_url:
            required = [
                self.postgres_host,
                self.postgres_port,
                self.postgres_db,
                self.postgres_user,
                self.postgres_password,
            ]
            if any(value is None for value in required):
                raise ValueError("Set DATABASE_URL or all POSTGRES_* settings in .env.")
            self.database_url = (
                f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        origins: list[str] = []
        if self.cors_allowed_origins:
            origins.extend(item.strip() for item in self.cors_allowed_origins.split(",") if item.strip())

        frontend_origin = self._normalize_origin(self.frontend_app_url)
        if frontend_origin:
            origins.append(frontend_origin)

        # Capacitor Android/iOS WebViews do not use the public frontend origin.
        # Keep the mobile shell able to reach the API without requiring extra
        # per-environment CORS tuning.
        origins.extend([
            "https://localhost",
            "http://localhost",
            "capacitor://localhost",
            "ionic://localhost",
        ])

        deduped: list[str] = []
        seen: set[str] = set()
        for origin in origins:
          if origin not in seen:
              seen.add(origin)
              deduped.append(origin)
        return deduped

    @staticmethod
    def _normalize_origin(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
