"""Full-text search over claims / citation statements (scite-parity WP2, F3).

A derived, non-mutating read-side view — like :mod:`interciter.services.projection`,
:mod:`interciter.services.graph`, and :mod:`interciter.services.citation_stats`. It
matches a keyword against the normalized claim text *and* the verbatim source passage
(scite searches inside citation statements, not just title/abstract), then exposes the
usual InterCiter facets so a reader can narrow by section, function, stance, resolution,
and year.

Design choices that mirror the rest of the codebase:

* the search unit is the current interpretation **head** of a claim occurrence — the
  head is derived at read time (an interpretation no other interpretation lists as a
  parent), never stored as a flag;
* function and stance stay SEPARATE dimensions; and
* text matching is case-insensitive via ``lower(col) LIKE lower(pattern)`` so it behaves
  the same on SQLite (dev) and PostgreSQL (prod) without relying on ``ILIKE``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import EvidenceRef, SearchFacets, SearchHit, SearchResults


@dataclass
class _Candidate:
    """A head interpretation that passed the text/year filter, with derived facets."""

    interp: models.ClaimInterpretation
    work: models.PaperWork
    passage: models.Passage
    section: str
    functions: set[str] = field(default_factory=set)
    stances: set[str] = field(default_factory=set)
    resolutions: set[str] = field(default_factory=set)


def _evidence_for_passage(session: Session, passage: models.Passage) -> EvidenceRef:
    version = session.get(models.PaperVersion, passage.paper_version_id)
    work_id = version.work_id if version else "unknown"
    return EvidenceRef(
        passage_id=passage.passage_id,
        paper_version_id=passage.paper_version_id,
        work_id=work_id,
        section=passage.section,
        verbatim_text=passage.verbatim_text,
        char_start=passage.char_start,
        char_end=passage.char_end,
    )


def _head_ids(session: Session) -> set[str]:
    """Interpretation ids that ARE a head (no other interpretation lists them parent)."""
    all_ids: set[str] = set()
    parent_ids: set[str] = set()
    for interp in session.scalars(select(models.ClaimInterpretation)):
        all_ids.add(interp.interpretation_id)
        parent_ids.update(interp.parent_interpretation_ids or [])
    return all_ids - parent_ids


def _candidates(
    session: Session,
    *,
    q: str,
    min_year: int | None,
    max_year: int | None,
) -> list[_Candidate]:
    """Head interpretations whose claim or source passage matches the text + year filter."""
    stmt = (
        select(models.ClaimInterpretation, models.Passage, models.PaperWork)
        .join(
            models.ClaimOccurrence,
            models.ClaimInterpretation.claim_occurrence_id
            == models.ClaimOccurrence.occurrence_id,
        )
        .join(
            models.Passage,
            models.ClaimOccurrence.passage_id == models.Passage.passage_id,
        )
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .join(
            models.PaperWork,
            models.PaperVersion.work_id == models.PaperWork.work_id,
        )
    )

    term = q.strip().lower()
    if term:
        pattern = f"%{term}%"
        stmt = stmt.where(
            or_(
                func.lower(models.ClaimInterpretation.normalized_text).like(pattern),
                func.lower(models.Passage.verbatim_text).like(pattern),
            )
        )
    if min_year is not None:
        stmt = stmt.where(models.PaperWork.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(models.PaperWork.year <= max_year)

    heads = _head_ids(session)
    rows = [
        (interp, passage, work)
        for interp, passage, work in session.execute(stmt).all()
        if interp.interpretation_id in heads
    ]

    # Pull every relation citing from the matched occurrences in one query (no N+1).
    occurrence_ids = {interp.claim_occurrence_id for interp, _, _ in rows}
    relations_by_occurrence: dict[str, list[models.RelationAssertion]] = {}
    if occurrence_ids:
        for assertion in session.scalars(
            select(models.RelationAssertion).where(
                models.RelationAssertion.citing_occurrence_id.in_(occurrence_ids)
            )
        ):
            relations_by_occurrence.setdefault(
                assertion.citing_occurrence_id, []
            ).append(assertion)

    candidates: list[_Candidate] = []
    for interp, passage, work in rows:
        cand = _Candidate(
            interp=interp,
            work=work,
            passage=passage,
            section=passage.section or "unspecified",
        )
        for assertion in relations_by_occurrence.get(interp.claim_occurrence_id, []):
            if assertion.function is not None:
                cand.functions.add(assertion.function.value)
            if assertion.stance is not None:
                cand.stances.add(assertion.stance.value)
            cand.resolutions.add(assertion.resolution.value)
        candidates.append(cand)
    return candidates


def _facets(candidates: list[_Candidate]) -> SearchFacets:
    section: Counter[str] = Counter()
    function: Counter[str] = Counter()
    stance: Counter[str] = Counter()
    resolution: Counter[str] = Counter()
    for cand in candidates:
        section[cand.section] += 1
        for value in cand.functions:
            function[value] += 1
        for value in cand.stances:
            stance[value] += 1
        for value in cand.resolutions:
            resolution[value] += 1
    return SearchFacets(
        section=dict(section),
        function=dict(function),
        stance=dict(stance),
        resolution=dict(resolution),
    )


def search_claims(
    session: Session,
    *,
    q: str = "",
    section: str | None = None,
    function: str | None = None,
    stance: str | None = None,
    resolution: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = 25,
    offset: int = 0,
) -> SearchResults:
    """Search claims by keyword with faceted filters.

    ``function``/``stance``/``resolution`` match a claim that has *at least one* relation
    with that value. Facet counts are computed over the text/year-matched set before the
    categorical filters, so every narrowing option a query allows stays visible.
    """
    candidates = _candidates(session, q=q, min_year=min_year, max_year=max_year)
    facets = _facets(candidates)

    def keep(cand: _Candidate) -> bool:
        if section is not None and cand.section.lower() != section.strip().lower():
            return False
        if function is not None and function not in cand.functions:
            return False
        if stance is not None and stance not in cand.stances:
            return False
        if resolution is not None and resolution not in cand.resolutions:
            return False
        return True

    matched = [cand for cand in candidates if keep(cand)]
    # Deterministic relevance: most recent first, then a stable text/id tiebreak.
    matched.sort(
        key=lambda c: (
            -(c.work.year or 0),
            (c.work.title or "").lower(),
            c.interp.normalized_text.lower(),
            c.interp.interpretation_id,
        )
    )

    total = len(matched)
    page = matched[max(0, offset) : max(0, offset) + limit]
    hits = [
        SearchHit(
            claim_id=cand.interp.interpretation_id,
            normalized_text=cand.interp.normalized_text,
            occurrence_id=cand.interp.claim_occurrence_id,
            interpretation_id=cand.interp.interpretation_id,
            work_id=cand.work.work_id,
            paper_title=cand.work.title,
            year=cand.work.year,
            section=cand.passage.section,
            function=sorted(cand.functions),
            stance=sorted(cand.stances),
            resolution=sorted(cand.resolutions),
            evidence=_evidence_for_passage(session, cand.passage),
        )
        for cand in page
    ]
    return SearchResults(
        query=q,
        total=total,
        limit=limit,
        offset=max(0, offset),
        hits=hits,
        facets=facets,
    )
