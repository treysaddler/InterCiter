"""Application configuration.

Settings are environment-driven so the same code runs against SQLite locally and
PostgreSQL in production. The design targets Postgres as the system of record; the
default here is a local SQLite file so the MVP runs with zero infrastructure.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INTERCITER_",
        env_file=".env",
        extra="ignore",
    )

    # SQLAlchemy URL. SQLite for local dev; swap for a postgresql+psycopg URL in prod.
    database_url: str = "sqlite:///./interciter.db"

    # Ingestion hardening: reject documents larger than this before parsing
    # (docs/architecture.md — file-size limits before parsing).
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MiB

    # Extraction pipeline identity, recorded on every ExtractionRun for provenance.
    extractor_model: str = "interciter-stub"
    extractor_provider: str = "local"
    extractor_model_version: str = "0.1.0"
    prompt_template_version: str = "stub-v1"

    # PMC Open Access fetching (evaluation gold set). NCBI asks that requests identify a
    # tool and contact email; an API key raises the rate limit from 3 to 10 req/s.
    ncbi_tool: str = "interciter"
    ncbi_email: str = ""
    ncbi_api_key: str | None = None
    # Local cache for fetched JATS XML (gitignored; keyed by PMCID). Paper text is not
    # redistributed — only annotations keyed to PMCID/DOI are.
    pmc_cache_dir: str = ".cache/pmc"

    # Emit SQL for debugging.
    echo_sql: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
