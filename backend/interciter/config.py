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

    # Semantic Scholar. The Academic Graph API is usable unauthenticated (shared global
    # pool); an API key raises limits and is *required* for the Datasets API. Per-paper
    # JSON is cached under ``s2_cache_dir``; bulk snapshots under ``s2_datasets_dir``
    # (both gitignored). Only identifiers/annotations and the small manifest are ever
    # committed — never fetched text or shards.
    s2_api_key: str | None = None
    s2_graph_base: str = "https://api.semanticscholar.org/graph/v1"
    s2_datasets_base: str = "https://api.semanticscholar.org/datasets/v1"
    s2_cache_dir: str = ".cache/s2"
    s2_datasets_dir: str = ".cache/s2-datasets"

    # ROBOKOP / NCATS Translator reference services (entity grounding + one-hop edges).
    # All cache-first; responses cached under ``robokop_cache_dir`` (gitignored).
    robokop_trapi_url: str = "https://automat.renci.org/robokopkg/1.5/query"
    node_norm_url: str = "https://nodenormalization-sri.renci.org"
    name_res_url: str = "https://name-resolution-sri.renci.org"
    robokop_cache_dir: str = ".cache/robokop"

    # SPECTER2 paper-level prefilter for cross-paper clustering. Gates which cross-paper
    # claim pairs are even compared; the claim-level decision itself stays token-overlap
    # (paper-level embeddings never assert claim equivalence — docs/architecture.md).
    # Gracefully disabled per-pair when either paper lacks a cached embedding.
    embedding_prefilter_enabled: bool = True
    embedding_prefilter_threshold: float = 0.5

    # Emit SQL for debugging.
    echo_sql: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
