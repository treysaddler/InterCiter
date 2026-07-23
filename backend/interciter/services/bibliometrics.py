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

import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import (
    AnnualProduction,
    AuthorMetric,
    AuthorMetrics,
    AuthorProductivity,
    BibliometricsSummary,
    BradfordZone,
    CitedDocument,
    CountryMetric,
    CountryMetrics,
    LotkaFit,
    LotkaPoint,
    SourceMetric,
    SourceMetrics,
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


# ---------------------------------------------------------------------------------
# Three-level metrics — authors / sources / countries (WP-B2)
# ---------------------------------------------------------------------------------


def _h_index(citation_counts: list[int]) -> int:
    """The h-index of a set of documents given their citation counts.

    ``h`` is the largest number such that ``h`` documents each have at least ``h``
    citations.
    """
    ordered = sorted(citation_counts, reverse=True)
    h = 0
    for rank, count in enumerate(ordered, start=1):
        if count >= rank:
            h = rank
        else:
            break
    return h


def _least_squares(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ordinary least-squares slope + intercept for ``y = slope*x + intercept``.

    Returns ``None`` when there are fewer than two points or the x-values are constant
    (a vertical fit is undefined).
    """
    n = len(xs)
    if n < 2:
        return None
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _author_work_ids(works: list[models.PaperWork]) -> dict[str, list[str]]:
    """Map each distinct author (normalized key) to the cohort work ids they appear on."""
    by_author: dict[str, list[str]] = {}
    for work in works:
        seen: set[str] = set()
        for name in work.authors or []:
            if not name or not name.strip():
                continue
            key = _author_key(name)
            if key in seen:  # a work counts once per author even if listed twice
                continue
            seen.add(key)
            by_author.setdefault(key, []).append(work.work_id)
    return by_author


def _lotka_fit(author_doc_counts: list[int]) -> LotkaFit:
    """Fit Lotka's law ``f(x) = C / x**n`` to the author-productivity distribution."""
    distribution = Counter(author_doc_counts)
    total_authors = len(author_doc_counts)
    points = [
        LotkaPoint(
            documents_written=docs,
            author_count=count,
            proportion=round(count / total_authors, 4) if total_authors else 0.0,
        )
        for docs, count in sorted(distribution.items())
    ]

    coefficient: float | None = None
    constant: float | None = None
    if len(distribution) >= 2:
        xs = [math.log10(docs) for docs in distribution]
        ys = [math.log10(count) for count in distribution.values()]
        fit = _least_squares(xs, ys)
        if fit is not None:
            slope, intercept = fit
            coefficient = round(-slope, 4)
            constant = round(10**intercept, 4)

    return LotkaFit(
        coefficient=coefficient,
        constant=constant,
        author_count=total_authors,
        points=points,
    )


def author_metrics(
    session: Session,
    *,
    work_ids: list[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> AuthorMetrics:
    """Author productivity, h-index, and the Lotka-law productivity distribution."""
    top_k = max(1, min(top_k, MAX_TOP_K))
    works = _load_cohort(session, work_ids, min_year, max_year)
    in_deg = _citation_in_degree(session)
    by_author = _author_work_ids(works)
    display = {_author_key(n): n.strip() for w in works for n in (w.authors or []) if n and n.strip()}

    metrics: list[AuthorMetric] = []
    for key, work_id_list in by_author.items():
        citations = [in_deg.get(wid, 0) for wid in work_id_list]
        metrics.append(
            AuthorMetric(
                name=display.get(key, key),
                document_count=len(work_id_list),
                total_citations=sum(citations),
                h_index=_h_index(citations),
            )
        )

    metrics.sort(key=lambda m: (-m.document_count, -m.h_index, -m.total_citations, m.name))
    lotka = _lotka_fit([m.document_count for m in metrics])
    return AuthorMetrics(author_count=len(metrics), authors=metrics[:top_k], lotka=lotka)


def _bradford_zone_map(source_articles: list[tuple[str, int]]) -> dict[str, int]:
    """Assign each source to a Bradford zone (1/2/3) by cumulative article thirds.

    Sources are taken in descending productivity order; the running article total is
    split into three equal parts, so zone 1 is the small "core" of prolific sources.
    """
    total = sum(count for _source, count in source_articles)
    if total == 0:
        return {}
    threshold = total / 3
    zones: dict[str, int] = {}
    cumulative = 0
    for source, count in source_articles:
        # Zone is decided by where this source's articles fall in the cumulative run.
        midpoint = cumulative + count / 2
        if midpoint <= threshold:
            zone = 1
        elif midpoint <= 2 * threshold:
            zone = 2
        else:
            zone = 3
        zones[source] = zone
        cumulative += count
    return zones


def source_metrics(
    session: Session,
    *,
    work_ids: list[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> SourceMetrics:
    """Source productivity, h-index impact, and Bradford's-law zones."""
    top_k = max(1, min(top_k, MAX_TOP_K))
    works = _load_cohort(session, work_ids, min_year, max_year)
    in_deg = _citation_in_degree(session)

    source_works: dict[str, list[str]] = {}
    for work in works:
        venue = (work.venue or "").strip()
        if venue:
            source_works.setdefault(venue, []).append(work.work_id)

    ranked = sorted(
        source_works.items(), key=lambda kv: (-len(kv[1]), kv[0])
    )
    zone_map = _bradford_zone_map([(s, len(ids)) for s, ids in ranked])

    sources: list[SourceMetric] = []
    for source, work_id_list in ranked:
        citations = [in_deg.get(wid, 0) for wid in work_id_list]
        sources.append(
            SourceMetric(
                source=source,
                document_count=len(work_id_list),
                total_citations=sum(citations),
                h_index=_h_index(citations),
                bradford_zone=zone_map.get(source, 3),
            )
        )

    zone_counter: Counter[int] = Counter()
    zone_articles: Counter[int] = Counter()
    for source, work_id_list in source_works.items():
        zone = zone_map.get(source, 3)
        zone_counter[zone] += 1
        zone_articles[zone] += len(work_id_list)
    bradford_zones = [
        BradfordZone(
            zone=zone,
            source_count=zone_counter.get(zone, 0),
            article_count=zone_articles.get(zone, 0),
        )
        for zone in (1, 2, 3)
    ]

    return SourceMetrics(
        source_count=len(source_works),
        sources=sources[:top_k],
        bradford_zones=bradford_zones,
    )


# A modest lexicon of country names + common aliases for parsing affiliation strings.
# Not exhaustive — an importer with structured country codes (WP-B6 OpenAlex) is the
# authoritative source; this heuristic covers free-text affiliation tails.
_COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "prc": "China",
    "p.r. china": "China",
    "p.r.china": "China",
    "russia": "Russia",
    "russian federation": "Russia",
}
_COUNTRIES = {
    "united states",
    "united kingdom",
    "china",
    "germany",
    "france",
    "japan",
    "canada",
    "australia",
    "italy",
    "spain",
    "netherlands",
    "switzerland",
    "sweden",
    "india",
    "brazil",
    "south korea",
    "russia",
    "belgium",
    "denmark",
    "norway",
    "finland",
    "austria",
    "poland",
    "portugal",
    "greece",
    "ireland",
    "israel",
    "turkey",
    "mexico",
    "argentina",
    "chile",
    "south africa",
    "egypt",
    "saudi arabia",
    "iran",
    "singapore",
    "new zealand",
    "taiwan",
    "hong kong",
    "czech republic",
    "hungary",
    "romania",
    "thailand",
    "malaysia",
    "indonesia",
    "pakistan",
    "colombia",
}


def _parse_country(affiliation: str) -> str | None:
    """Best-effort country extraction from a free-text affiliation string.

    Scans comma-separated segments (last segment first, where a country usually sits)
    and the whole string against a country lexicon + alias map. Returns ``None`` when
    no known country is recognized.
    """
    if not affiliation:
        return None
    segments = [seg.strip().lower().rstrip(".") for seg in affiliation.split(",")]
    for seg in reversed(segments):
        if not seg:
            continue
        if seg in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[seg]
        if seg in _COUNTRIES:
            return _title_country(seg)
    return None


def _title_country(seg: str) -> str:
    """Title-case a multi-word country name from the lexicon."""
    return " ".join(word.capitalize() for word in seg.split())


def _work_countries(work: models.PaperWork) -> set[str]:
    """The distinct set of countries recognized across a work's affiliation strings."""
    countries: set[str] = set()
    for aff in work.author_affiliations or []:
        country = _parse_country(aff)
        if country:
            countries.add(country)
    return countries


def country_metrics(
    session: Session,
    *,
    work_ids: list[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> CountryMetrics:
    """Country production with single- vs multi-country (SCP/MCP) collaboration split."""
    top_k = max(1, min(top_k, MAX_TOP_K))
    works = _load_cohort(session, work_ids, min_year, max_year)

    scp: Counter[str] = Counter()
    mcp: Counter[str] = Counter()
    documents_with_country = 0
    multi_country_docs = 0
    for work in works:
        countries = _work_countries(work)
        if not countries:
            continue
        documents_with_country += 1
        is_multi = len(countries) > 1
        if is_multi:
            multi_country_docs += 1
        for country in countries:
            if is_multi:
                mcp[country] += 1
            else:
                scp[country] += 1

    all_countries = set(scp) | set(mcp)
    metrics: list[CountryMetric] = []
    for country in all_countries:
        s = scp.get(country, 0)
        m = mcp.get(country, 0)
        total = s + m
        metrics.append(
            CountryMetric(
                country=country,
                document_count=total,
                single_country_pubs=s,
                multi_country_pubs=m,
                mcp_ratio=round(m / total, 4) if total else 0.0,
            )
        )
    metrics.sort(key=lambda c: (-c.document_count, c.country))

    intl_pct = (
        round(multi_country_docs / documents_with_country * 100, 2)
        if documents_with_country
        else None
    )
    return CountryMetrics(
        country_count=len(all_countries),
        documents_with_country=documents_with_country,
        international_co_authorship_pct=intl_pct,
        countries=metrics[:top_k],
    )