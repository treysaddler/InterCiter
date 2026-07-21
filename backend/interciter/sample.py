"""Bundled sample corpus for demonstrating the vertical slice.

Ingests two open-access papers in order: an antecedent result paper (B), then a citing
paper (A) that cites B. Because B is ingested first, A's citation to B resolves at the
**claim level** (one confidently matched target claim), while A's other citations fall
back to the honest **paper level** against metadata stubs — exercising the full
resolution/abstention spectrum in one run.
"""

from __future__ import annotations

from importlib import resources

from sqlalchemy.orm import Session

from .config import get_settings
from .ingestion.pipeline import IngestResult, ingest_paper


def _load(name: str) -> str:
    return (
        resources.files("interciter.data.sample").joinpath(name).read_text(encoding="utf-8")
    )


def seed_sample_corpus(session: Session) -> list[str]:
    settings = get_settings()
    lines: list[str] = []
    for name in ("paper_b.xml", "paper_a.xml"):
        result: IngestResult = ingest_paper(session, xml=_load(name), settings=settings)
        lines.append(
            f"{name}: work={result.work_id} claims={result.interpretations} "
            f"relations={result.relation_assertions} "
            f"(claim_resolved={result.claim_resolved}, paper_resolved={result.paper_resolved})"
        )
    return lines
