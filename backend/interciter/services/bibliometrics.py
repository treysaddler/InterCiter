"""Corpus-level descriptive analytics — bibliometrix "Main Information" (WP-B1).

A derived, non-mutating read-side view (like :mod:`interciter.services.projection`,
:mod:`interciter.services.graph`, and :mod:`interciter.services.citation_stats`): it
rolls up the existing metadata on :class:`~interciter.models.PaperWork` (authors,
venue, year) plus the citation graph into the aggregate descriptive statistics
bibliometrix calls "Main Information" — timespan, source / document / author counts,
annual production + growth rate, average citations per document, and the most
productive authors / sources and most cited documents.

This is the corpus *metadata* lens that complements — and never replaces —
InterCiter's claim-level function + stance + provenance rigor. Nothing here mutates a
scientific assertion; it is a pure projection over a cohort of works (an explicit
``work_ids`` set, else the whole database) optionally narrowed by publication year.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import (
    AnnualProduction,
    AuthorProductivity,
    BibliometricsSummary,
    CitedDocument,
    SourceProductivity,
)

DEFAULT_TOP_K = 10
MAX_TOP_K = 50


def _author_key(name: str) -> str:
    """Normalized equality key for an author display name (same rule as graph)."""
    return name.strip().casefold()


def _citation_in_degree(session: Session) -> dict[str, int]:
    """Global citation in-degree per work: how many DISTINCT works cite each one.

    Unions both citation sources (passage-grounded ``CitationMention`` and
    bibliographic ``CitationEdge``) and dedupes to distinct (citing, cited) pairs so a
    work cited from two sources by the same citing work still counts once.
    """
    pairs: set[tuple[str, str]] = set()

    mention_stmt = (
        select(models.PaperVersion.work_id, models.CitationMention.cited_work_id)
        .join(
            models.Passage,
            models.CitationMention.passage_id == models.Passage.passage_id,
        )
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .where(models.CitationMention.cited_work_id.is_not(None))
    )
    for citing, cited in session.execute(mention_stmt):
        if citing and cited and citing != cited:
            pairs.add((citing, cited))

    for edge in session.scalars(select(models.CitationEdge)):
        citing, cited = edge.citing_work_id, edge.cited_work_id
        if citing and cited and citing != cited:
            pairs.add((citing, cited))

    in_deg: dict[str, int] = {}
    for _citing, cited in pairs:
        in_deg[cited] = in_deg.get(cited, 0) + 1
    return in_deg


def _load_cohort(
    session: Session,
    work_ids: list[str] | None,
    min_year: int | None,
    max_year: int | None,
) -> list[models.PaperWork]:
    """Resolve the cohort of works: an explicit id set (else all), filtered by year.

    When a year bound is given, works whose ``year`` is null or outside the range are
    excluded — a document that can't be placed on the timeline can't be counted in a
    year-scoped cohort.
    """
    stmt = select(models.PaperWork)
    if work_ids is not None:
        wanted = set(work_ids)
        if not wanted:
            return []
        stmt = stmt.where(models.PaperWork.work_id.in_(wanted))
    works = list(session.scalars(stmt))

    if min_year is not None or max_year is not None:
        filtered: list[models.PaperWork] = []
        for work in works:
            if work.year is None:
                continue
            if min_year is not None and work.year < min_year:
                continue
            if max_year is not None and work.year > max_year:
                continue
            filtered.append(work)
        return filtered
    return works


def _annual_growth_rate(counts: dict[int, int], min_year: int, max_year: int) -> float | None:
    """Compound annual growth rate (%) of annual production, bibliometrix-style.

    ``CAGR = (P(t_n) / P(t_0)) ** (1 / (t_n - t_0)) - 1``, where ``P`` is the document
    count in the first and last years that carry any production. ``None`` when the
    span is a single year or the first year has no production.
    """
    span = max_year - min_year
    first = counts.get(min_year, 0)
    last = counts.get(max_year, 0)
    if span <= 0 or first <= 0 or last <= 0:
        return None
    return round(((last / first) ** (1 / span) - 1) * 100, 2)


def corpus_summary(
    session: Session,
    *,
    work_ids: list[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> BibliometricsSummary:
    """The corpus "Main Information" descriptive rollup over a cohort of works."""
    top_k = max(1, min(top_k, MAX_TOP_K))
    works = _load_cohort(session, work_ids, min_year, max_year)
    document_count = len(works)

    if document_count == 0:
        return BibliometricsSummary(
            document_count=0,
            source_count=0,
            author_count=0,
            author_appearances=0,
            co_authors_per_doc=0.0,
            single_authored_count=0,
            avg_citations_per_doc=0.0,
            total_citations=0,
            documents_without_year=0,
        )

    # Sources (distinct non-empty venue) + per-source production.
    source_counter: Counter[str] = Counter()
    for work in works:
        venue = (work.venue or "").strip()
        if venue:
            source_counter[venue] += 1

    # Authors: appearances (total slots), distinct people, and per-author production.
    author_appearances = 0
    single_authored_count = 0
    author_docs: Counter[str] = Counter()
    author_display: dict[str, str] = {}
    for work in works:
        names = [n for n in (work.authors or []) if n and n.strip()]
        author_appearances += len(names)
        if len(names) == 1:
            single_authored_count += 1
        seen: set[str] = set()
        for name in names:
            key = _author_key(name)
            author_display.setdefault(key, name.strip())
            if key not in seen:  # one document counts once per distinct author
                seen.add(key)
                author_docs[key] += 1

    author_count = len(author_docs)
    co_authors_per_doc = round(author_appearances / document_count, 2)

    # Years / annual production.
    year_counts: Counter[int] = Counter()
    documents_without_year = 0
    for work in works:
        if work.year is None:
            documents_without_year += 1
        else:
            year_counts[work.year] += 1

    if year_counts:
        summary_min_year = min(year_counts)
        summary_max_year = max(year_counts)
        annual_production = [
            AnnualProduction(year=year, document_count=year_counts[year])
            for year in range(summary_min_year, summary_max_year + 1)
        ]
        growth_rate = _annual_growth_rate(
            dict(year_counts), summary_min_year, summary_max_year
        )
    else:
        summary_min_year = summary_max_year = None
        annual_production = []
        growth_rate = None

    # Citations: global in-degree restricted to the cohort.
    in_deg = _citation_in_degree(session)
    cohort_ids = {work.work_id for work in works}
    cited_counts = {wid: in_deg.get(wid, 0) for wid in cohort_ids}
    total_citations = sum(cited_counts.values())
    avg_citations_per_doc = round(total_citations / document_count, 2)

    work_by_id = {work.work_id: work for work in works}
    top_cited = sorted(
        (wid for wid in cohort_ids if cited_counts[wid] > 0),
        key=lambda wid: (-cited_counts[wid], work_by_id[wid].title or "", wid),
    )[:top_k]
    top_cited_documents = [
        CitedDocument(
            work_id=wid,
            title=work_by_id[wid].title,
            year=work_by_id[wid].year,
            citation_count=cited_counts[wid],
        )
        for wid in top_cited
    ]

    top_authors = [
        AuthorProductivity(name=author_display[key], document_count=count)
        for key, count in author_docs.most_common(top_k)
    ]
    top_sources = [
        SourceProductivity(source=source, document_count=count)
        for source, count in source_counter.most_common(top_k)
    ]

    return BibliometricsSummary(
        document_count=document_count,
        source_count=len(source_counter),
        author_count=author_count,
        author_appearances=author_appearances,
        co_authors_per_doc=co_authors_per_doc,
        single_authored_count=single_authored_count,
        min_year=summary_min_year,
        max_year=summary_max_year,
        annual_growth_rate=growth_rate,
        avg_citations_per_doc=avg_citations_per_doc,
        total_citations=total_citations,
        documents_without_year=documents_without_year,
        annual_production=annual_production,
        top_authors=top_authors,
        top_sources=top_sources,
        top_cited_documents=top_cited_documents,
    )
