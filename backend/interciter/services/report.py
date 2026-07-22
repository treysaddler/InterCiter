"""Per-paper citation report aggregation (scite-parity WP3, F4).

This composes citation-stats (WP1) into a report-friendly view with:
- optional faceted filters over citation statements,
- a citations-over-time timeline (bucketed by citing-work year), and
- a conflicting-stance summary.

Read-side only: derived and non-mutating.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from .. import enums, models
from ..schemas import (
    CitationStatement,
    CitationTallies,
    PaperReport,
    ReportAppliedFilters,
    ReportConflictSummary,
    ReportFacets,
    ReportTimelinePoint,
)
from . import citation_stats


def _tallies(statements: list[CitationStatement]) -> CitationTallies:
    by_stance: Counter[str] = Counter()
    by_function: Counter[str] = Counter()
    by_resolution: Counter[str] = Counter()
    by_section: Counter[str] = Counter()
    abstained = 0
    for statement in statements:
        if statement.stance is not None:
            by_stance[statement.stance.value] += 1
        if statement.function is not None:
            by_function[statement.function.value] += 1
        if statement.stance is None and statement.function is None:
            abstained += 1
        by_resolution[statement.resolution.value] += 1
        by_section[statement.section or "unspecified"] += 1
    return CitationTallies(
        total=len(statements),
        by_stance=dict(by_stance),
        by_function=dict(by_function),
        by_resolution=dict(by_resolution),
        by_section=dict(by_section),
        abstained=abstained,
    )


def _year_lookup(session: Session, statements: list[CitationStatement]) -> dict[str, int | None]:
    work_ids = {s.citing_work_id for s in statements if s.citing_work_id}
    if not work_ids:
        return {}
    works = session.query(models.PaperWork).filter(models.PaperWork.work_id.in_(work_ids)).all()
    return {w.work_id: w.year for w in works}


def _facets(
    statements: list[CitationStatement], year_by_work: dict[str, int | None]
) -> ReportFacets:
    section: Counter[str] = Counter()
    function: Counter[str] = Counter()
    stance: Counter[str] = Counter()
    resolution: Counter[str] = Counter()
    year: Counter[str] = Counter()

    for statement in statements:
        section[statement.section or "unspecified"] += 1
        if statement.function is not None:
            function[statement.function.value] += 1
        if statement.stance is not None:
            stance[statement.stance.value] += 1
        resolution[statement.resolution.value] += 1

        y = year_by_work.get(statement.citing_work_id or "")
        if y is not None:
            year[str(y)] += 1

    return ReportFacets(
        section=dict(section),
        function=dict(function),
        stance=dict(stance),
        resolution=dict(resolution),
        year=dict(year),
    )


def _matches(
    statement: CitationStatement,
    *,
    year: int | None,
    section: str | None,
    function: str | None,
    stance: str | None,
    resolution: str | None,
    min_year: int | None,
    max_year: int | None,
) -> bool:
    if section and (statement.section or "unspecified") != section:
        return False
    if function and (statement.function is None or statement.function.value != function):
        return False
    if stance and (statement.stance is None or statement.stance.value != stance):
        return False
    if resolution and statement.resolution.value != resolution:
        return False
    if min_year is not None:
        if year is None or year < min_year:
            return False
    if max_year is not None:
        if year is None or year > max_year:
            return False
    return True


def _timeline(
    statements: list[CitationStatement], year_by_work: dict[str, int | None]
) -> list[ReportTimelinePoint]:
    statement_count: Counter[int] = Counter()
    works_by_year: dict[int, set[str]] = defaultdict(set)

    for statement in statements:
        work_id = statement.citing_work_id
        if not work_id:
            continue
        year = year_by_work.get(work_id)
        if year is None:
            continue
        statement_count[year] += 1
        works_by_year[year].add(work_id)

    return [
        ReportTimelinePoint(
            year=year,
            statement_count=statement_count[year],
            citing_work_count=len(works_by_year[year]),
        )
        for year in sorted(statement_count.keys())
    ]


def _conflict_summary(statements: list[CitationStatement]) -> ReportConflictSummary:
    supporting = 0
    contradicting = 0
    neutral_or_unclear = 0
    stances_by_work: dict[str, set[enums.RelationStance]] = defaultdict(set)

    for statement in statements:
        if statement.stance == enums.RelationStance.support:
            supporting += 1
        elif statement.stance == enums.RelationStance.contradict:
            contradicting += 1
        else:
            neutral_or_unclear += 1

        if statement.citing_work_id and statement.stance in {
            enums.RelationStance.support,
            enums.RelationStance.contradict,
        }:
            stances_by_work[statement.citing_work_id].add(statement.stance)

    conflicting_citing_work_count = sum(
        1
        for stances in stances_by_work.values()
        if enums.RelationStance.support in stances
        and enums.RelationStance.contradict in stances
    )

    return ReportConflictSummary(
        has_conflicting_stances=supporting > 0 and contradicting > 0,
        supporting_statements=supporting,
        contradicting_statements=contradicting,
        neutral_or_unclear_statements=neutral_or_unclear,
        conflicting_citing_work_count=conflicting_citing_work_count,
    )


def paper_report_for_work(
    session: Session,
    work_id: str,
    *,
    section: str | None = None,
    function: str | None = None,
    stance: str | None = None,
    resolution: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
) -> PaperReport:
    """Build a report for a work from incoming relation assertions.

    Raises :class:`KeyError` when the work does not exist.
    """
    stats = citation_stats.citation_stats_for_work(session, work_id)
    all_statements = stats.statements
    year_by_work = _year_lookup(session, all_statements)

    filtered = [
        statement
        for statement in all_statements
        if _matches(
            statement,
            year=year_by_work.get(statement.citing_work_id or ""),
            section=section,
            function=function,
            stance=stance,
            resolution=resolution,
            min_year=min_year,
            max_year=max_year,
        )
    ]

    return PaperReport(
        work_id=work_id,
        total_statements=len(all_statements),
        filtered_statements=len(filtered),
        facets=_facets(all_statements, year_by_work),
        applied_filters=ReportAppliedFilters(
            section=section,
            function=function,
            stance=stance,
            resolution=resolution,
            min_year=min_year,
            max_year=max_year,
        ),
        tallies=_tallies(filtered),
        timeline=_timeline(filtered, year_by_work),
        conflict_summary=_conflict_summary(filtered),
        statements=filtered,
    )
