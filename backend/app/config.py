"""Centralized application settings.

All configuration is read from environment variables (see `.env.example` at
the repo root). We use `pydantic-settings` so misconfiguration fails fast and
loudly at process startup instead of deep inside a graph node.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    # Classification and field extraction should be as deterministic as
    # possible -- this is tax data entry, not creative writing.
    llm_temperature: float = 0.0

    # --- Postgres (prompts, clients/documents, LangGraph checkpoints) ---
    # SQLAlchemy (sync engine) uses the psycopg3 dialect: postgresql+psycopg://
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/tax_intake"
    )
    # AsyncPostgresSaver needs a plain psycopg-style DSN (no "+psycopg" driver
    # suffix); we strip it in db/checkpointer.py.

    # --- Documents --------------------------------------------------------
    # Where uploaded documents are stored (git-ignored). Relative paths are
    # resolved from the backend/ working directory.
    upload_dir: str = "./data/uploads"
    # Where the bundled synthetic sample documents live, so the "run a
    # sample document" zero-setup demo path and the seed scripts can find
    # them. Defaults to the repo-root `sample-data/` folder one level up
    # from `backend/`; overridden to `/app/sample-data` in Docker (see
    # docker-compose.yml, which mounts it read-only).
    sample_data_dir: str = "../sample-data"

    # --- Cross-check policy -------------------------------------------------
    # Fuzzy counterparty-name match threshold (difflib SequenceMatcher ratio,
    # 0-1) used by app/tools/organizer.py when matching an extracted
    # employer/payer/partnership/bank name against a client's
    # expected-documents checklist and previously received documents.
    counterparty_match_threshold: float = 0.72

    # --- API ---------------------------------------------------------------
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
