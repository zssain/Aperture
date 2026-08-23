"""Application configuration.

Loaded from the environment via ``pydantic-settings``. Required variables have no
default: if ``DATABASE_URL`` or ``FRONTEND_ORIGIN`` is missing the process fails
loudly at startup with a validation error naming the variable, rather than falling
back to a silent (and wrong) default.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, resolved by absolute path so it loads regardless of the process's
# working directory (the backend runs from backend/, the .env lives at the repo root).
# Real environment variables still take precedence over this file (e.g. in CI).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Typed application settings sourced from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "aperture"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Session cookie. Secure=True is correct for production/HTTPS; set false only for
    # local HTTP development. Idle TTL is 8 hours (invariant of the auth stage).
    session_cookie_name: str = "aperture_session"
    session_cookie_secure: bool = True
    session_idle_ttl_seconds: int = 8 * 60 * 60

    # Required — no default. Missing values raise at startup.
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host/db",
    )
    frontend_origin: str = Field(
        ...,
        description="Allowed CORS origin for the SPA, e.g. http://localhost:5173",
    )

    # Connection-pool sizing (per process). Keep the product of (pool_size +
    # max_overflow) x processes under the host's connection cap. Supabase's direct
    # connection is small (~15-60 by plan); its session pooler is larger — size
    # accordingly via env.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # asyncpg caches prepared statements per connection. Behind a transaction-mode
    # pooler (Supabase Supavisor/PgBouncer, port 6543) pooled server connections are
    # shared across clients, so those cached handles break at runtime. Set to 0 for any
    # pooled connection. None = driver default (fine for a direct/local connection).
    db_statement_cache_size: int | None = None

    # Event-driven decisioning. A short delay coalesces bursts without losing any
    # ledger events; queue change views intentionally show only recent changes.
    redecision_debounce_seconds: int = 5
    decision_change_window_days: int = 30
    demo_events_enabled: bool = False
    policy_simulation_minimum_snapshots: int = 100
    policy_bulk_redecision_chunk_size: int = 250

    # Notice generation is deliberately opt-in. Templates remain the production default.
    llm_notices_enabled: bool = False
    llm_notice_timeout_seconds: float = 5.0
    llm_provider: str = "noop"
    embedding_provider: str = "noop"
    embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    vector_similarity_floor: float = 0.82
    allow_external_embeddings: bool = False
    aws_region: str = "ap-south-1"
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    # Google Gemini. The key is read from the repo-root .env (Gemini_api_Key,
    # matched case-insensitively). gemini-embedding-001 supports outputDimensionality,
    # so it is reduced to `embedding_dimension` to match the merchant catalogue column.
    # Prefer the durable AIza-style key (Gemini_New_Api_Key); fall back to the older
    # Gemini_api_Key. AIza keys are more reliable than short-lived OAuth tokens.
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("gemini_new_api_key", "gemini_api_key"),
    )
    gemini_embedding_model_id: str = "gemini-embedding-001"
    gemini_model_id: str = "gemini-flash-lite-latest"
    # OpenAI (chat completions) — an alternative notice LLM.
    openai_api_key: str | None = None
    openai_model_id: str = "gpt-4o-mini"
    llm_max_tokens: int = 1200
    secret_provider: str = "environment"
    aws_secret_id: str | None = None
    kms_key_arn: str | None = None
    demo_seed_enabled: bool = False

    # Raw evidence is short lived and is never served from the application web root.
    upload_directory: Path = Path("/tmp/aperture-uploads")
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_max_rows: int = 20_000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (validated on first access)."""
    return Settings()


settings: Settings = get_settings()
