"""Semantic Scholar enrichment — non-destructive backfill onto the system of record.

Phase 2 of the external-data integration (docs/external-data-integration.md). This layer
turns raw Academic Graph responses into safe, additive updates on existing
``PaperWork`` rows:

* backfill ``s2_corpus_id`` (the design's identifier bridge);
* fill **only null** metadata gaps (title, authors, venue, year, doi, pmid) — never
  overwrite a value the graph already holds, since bibliographic metadata is not a
  scientific assertion but is still authoritative once set;
* cache the paper's SPECTER2 embedding as a sidecar (paper-level narrowing only);
* expose resolved reference links (contexts + intents) as structured records for
  later persistence once the schema carries ``source_metadata`` (Phase 5).

No claim, occurrence, interpretation, relation, or cluster is touched here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..ingestion import semantic_scholar as s2


@dataclass
class EnrichmentResult:
    work_id: str
    s2_id_used: str | None = None
    s2_corpus_id: str | None = None
    fields_filled: list[str] = field(default_factory=list)
    embedding_dims: int = 0
    tldr: str | None = None
    reference_links: int = 0
    skipped_reason: str | None = None


def s2_id_for_work(work: models.PaperWork) -> str | None:
    """Best available Academic-Graph id for a work, or ``None`` if unidentifiable."""
    if work.doi:
        return f"DOI:{work.doi}"
    if work.pmid:
        return f"PMID:{work.pmid}"
    if work.s2_corpus_id:
        return f"CorpusId:{work.s2_corpus_id}"
    return None


def _embedding_path(settings: Settings, corpus_id: str) -> Path:
    directory = Path(settings.s2_cache_dir) / "embeddings"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{corpus_id}.json"


def cache_embedding(
    corpus_id: str,
    vector: list[float],
    *,
    settings: Settings | None = None,
) -> Path:
    """Persist a SPECTER2 vector as a sidecar keyed by corpusId; return its path."""
    settings = settings or get_settings()
    path = _embedding_path(settings, corpus_id)
    path.write_text(json.dumps({"model": "specter_v2", "vector": vector}), encoding="utf-8")
    return path


def load_embedding(
    corpus_id: str, *, settings: Settings | None = None
) -> list[float] | None:
    settings = settings or get_settings()
    path = _embedding_path(settings, corpus_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("vector")


def _author_names(paper: dict) -> list[str]:
    return [a["name"] for a in paper.get("authors") or [] if a.get("name")]


def reference_links(
    paper_id: str,
    *,
    max_records: int | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Return normalized reference records (contexts + intents) for later persistence.

    Pure read: shapes each resolved reference into
    ``{cited_corpus_id, cited_doi, cited_pmid, cited_title, contexts, intents,
    is_influential}``. Intents are Semantic Scholar's labels — kept raw as weak
    supervision, never mapped onto InterCiter's function/stance ontology here.
    """
    settings = settings or get_settings()
    out: list[dict] = []
    for ref in s2.get_references(
        paper_id, max_records=max_records, settings=settings, use_cache=use_cache
    ):
        cited = ref.get("citedPaper") or {}
        ext = cited.get("externalIds") or {}
        corpus = ext.get("CorpusId")
        out.append(
            {
                "cited_corpus_id": str(corpus) if corpus is not None else None,
                "cited_doi": ext.get("DOI"),
                "cited_pmid": ext.get("PubMed"),
                "cited_title": cited.get("title"),
                "contexts": ref.get("contexts") or [],
                "intents": ref.get("intents") or [],
                "is_influential": bool(ref.get("isInfluential")),
            }
        )
    return out


def enrich_work(
    session: Session,
    work: models.PaperWork,
    *,
    fetch_embedding: bool = True,
    fetch_references: bool = False,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> EnrichmentResult:
    """Backfill identifiers + metadata gaps on a single work from Semantic Scholar.

    Additive only: fills ``s2_corpus_id`` and any null title/authors/venue/year/doi/pmid.
    Existing values are left untouched. Does not commit — the caller owns the session.
    """
    settings = settings or get_settings()
    result = EnrichmentResult(work_id=work.work_id)

    s2_id = s2_id_for_work(work)
    if s2_id is None:
        result.skipped_reason = "no DOI/PMID/corpusId to resolve"
        return result
    result.s2_id_used = s2_id

    paper = s2.get_paper(s2_id, settings=settings, use_cache=use_cache)
    external = paper.get("externalIds") or {}

    corpus_id = external.get("CorpusId")
    if corpus_id is not None and not work.s2_corpus_id:
        work.s2_corpus_id = str(corpus_id)
        result.fields_filled.append("s2_corpus_id")
    result.s2_corpus_id = work.s2_corpus_id

    if not work.doi and external.get("DOI"):
        work.doi = external["DOI"]
        result.fields_filled.append("doi")
    if not work.pmid and external.get("PubMed"):
        work.pmid = external["PubMed"]
        result.fields_filled.append("pmid")
    if not work.title and paper.get("title"):
        work.title = paper["title"]
        result.fields_filled.append("title")
    if not work.authors and _author_names(paper):
        work.authors = _author_names(paper)
        result.fields_filled.append("authors")
    if not work.venue and paper.get("venue"):
        work.venue = paper["venue"]
        result.fields_filled.append("venue")
    if not work.year and paper.get("year"):
        work.year = paper["year"]
        result.fields_filled.append("year")

    tldr = paper.get("tldr") or {}
    result.tldr = tldr.get("text")

    if fetch_embedding and work.s2_corpus_id:
        vector = s2.get_embedding(s2_id, settings=settings, use_cache=use_cache)
        if vector:
            cache_embedding(work.s2_corpus_id, vector, settings=settings)
            result.embedding_dims = len(vector)

    if fetch_references:
        result.reference_links = len(
            reference_links(s2_id, settings=settings, use_cache=use_cache)
        )

    return result


def backfill_all(
    session: Session,
    *,
    limit: int | None = None,
    fetch_embedding: bool = True,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[EnrichmentResult]:
    """Enrich every work still missing an ``s2_corpus_id``. Commits once at the end."""
    settings = settings or get_settings()
    stmt = select(models.PaperWork).where(models.PaperWork.s2_corpus_id.is_(None))
    if limit is not None:
        stmt = stmt.limit(limit)
    results: list[EnrichmentResult] = []
    for work in session.scalars(stmt):
        results.append(
            enrich_work(
                session,
                work,
                fetch_embedding=fetch_embedding,
                settings=settings,
                use_cache=use_cache,
            )
        )
    session.commit()
    return results
