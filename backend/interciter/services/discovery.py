"""Seed-based discovery — ranked candidate papers connected to a seed set.

Litmaps-parity WP-L1. Given one or more seed works we already hold, this pulls each
seed's resolved references from Semantic Scholar and ranks the cited papers by how many
seeds reference them (co-reference / bibliographic-coupling degree). The result is the
"important papers you're likely missing" list that powers Litmaps-style discovery.

Deliberately non-authoritative and non-mutating: like the graph expansion it performs a
network read against Semantic Scholar, but — unlike expansion — it does NOT persist stub
works or edges. It only *reports* candidates. Resolution to an existing in-corpus work is
best-effort by DOI / PMID / corpusId so the UI can deep-link papers we already have, and
suggest ingestion for the ones we don't.

The connection metric is intentionally simple and explainable (a count of seeds that
cite the candidate). A SPECTER2 embedding rerank is a documented future extension; it is
omitted here so discovery stays deterministic and offline-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..schemas import DiscoveryCandidate, DiscoveryResult
from . import enrichment

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
DEFAULT_REFS_PER_SEED = 200
MAX_REFS_PER_SEED = 1000


@dataclass
class _Agg:
    """Accumulator for a candidate as it is seen across multiple seeds' references."""

    key: str
    corpus_id: str | None = None
    doi: str | None = None
    pmid: str | None = None
    title: str | None = None
    year: int | None = None
    is_influential: bool = False
    seeds: set[str] = field(default_factory=set)


def _link_key(link: dict) -> str | None:
    """A stable dedup key for a reference; ``None`` if it carries no usable identifier."""
    for field_name in ("cited_corpus_id", "cited_doi", "cited_pmid"):
        value = link.get(field_name)
        if value:
            return f"{field_name}:{value}"
    return None


def _external_id(agg: _Agg) -> str | None:
    if agg.corpus_id:
        return f"CorpusId:{agg.corpus_id}"
    if agg.doi:
        return f"DOI:{agg.doi}"
    if agg.pmid:
        return f"PMID:{agg.pmid}"
    return None


def _resolve_work(session: Session, agg: _Agg) -> models.PaperWork | None:
    conditions = []
    if agg.doi:
        conditions.append(models.PaperWork.doi == agg.doi)
    if agg.pmid:
        conditions.append(models.PaperWork.pmid == agg.pmid)
    if agg.corpus_id:
        conditions.append(models.PaperWork.s2_corpus_id == agg.corpus_id)
    if not conditions:
        return None
    return session.scalars(select(models.PaperWork).where(or_(*conditions))).first()


def discover_from_seeds(
    session: Session,
    seed_work_ids: list[str],
    *,
    limit: int = DEFAULT_LIMIT,
    min_year: int | None = None,
    refs_per_seed: int = DEFAULT_REFS_PER_SEED,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> DiscoveryResult:
    """Rank the papers most connected to ``seed_work_ids`` by co-reference degree.

    Raises :class:`KeyError` if any seed work id does not exist.
    """
    settings = settings or get_settings()
    limit = max(1, min(limit, MAX_LIMIT))
    refs_per_seed = max(1, min(refs_per_seed, MAX_REFS_PER_SEED))

    seeds: list[models.PaperWork] = []
    for wid in dict.fromkeys(seed_work_ids):  # de-duplicate, preserve order
        work = session.get(models.PaperWork, wid)
        if work is None:
            raise KeyError(wid)
        seeds.append(work)

    # Identifier values of the seeds themselves — never recommend a seed back to the user.
    seed_id_values: set[str] = set()
    for work in seeds:
        for value in (work.s2_corpus_id, work.doi, work.pmid):
            if value:
                seed_id_values.add(str(value))

    aggregates: dict[str, _Agg] = {}
    seeds_resolved = 0
    skipped: list[str] = []

    for work in seeds:
        s2_id = enrichment.s2_id_for_work(work)
        if s2_id is None:
            skipped.append(work.work_id)
            continue
        seeds_resolved += 1
        links = enrichment.reference_links(
            s2_id, max_records=refs_per_seed, settings=settings, use_cache=use_cache
        )
        for link in links:
            corpus = link.get("cited_corpus_id")
            doi = link.get("cited_doi")
            pmid = link.get("cited_pmid")
            if (
                (corpus and corpus in seed_id_values)
                or (doi and doi in seed_id_values)
                or (pmid and pmid in seed_id_values)
            ):
                continue
            key = _link_key(link)
            if key is None:
                continue  # unidentifiable reference — cannot dedupe or deep-link
            agg = aggregates.get(key)
            if agg is None:
                agg = _Agg(
                    key=key,
                    corpus_id=corpus,
                    doi=doi,
                    pmid=pmid,
                    title=link.get("cited_title"),
                    year=link.get("cited_year"),
                )
                aggregates[key] = agg
            agg.seeds.add(work.work_id)
            if link.get("is_influential"):
                agg.is_influential = True
            if agg.title is None and link.get("cited_title"):
                agg.title = link.get("cited_title")
            if agg.year is None and link.get("cited_year") is not None:
                agg.year = link.get("cited_year")

    candidates: list[DiscoveryCandidate] = []
    for agg in aggregates.values():
        existing = _resolve_work(session, agg)
        year = agg.year if agg.year is not None else (existing.year if existing else None)
        if min_year is not None and year is not None and year < min_year:
            continue
        candidates.append(
            DiscoveryCandidate(
                work_id=existing.work_id if existing else None,
                external_id=_external_id(agg),
                title=(existing.title if existing and existing.title else agg.title),
                year=year,
                connection_score=len(agg.seeds),
                supporting_seed_ids=sorted(agg.seeds),
                is_influential=agg.is_influential,
                in_corpus=existing is not None,
            )
        )

    # Most-connected first; influential references break ties; then title for stability.
    candidates.sort(
        key=lambda c: (-c.connection_score, not c.is_influential, (c.title or "").lower())
    )
    return DiscoveryResult(
        seed_work_ids=[w.work_id for w in seeds],
        candidates=candidates[:limit],
        seeds_resolved=seeds_resolved,
        skipped_seed_ids=skipped,
    )
