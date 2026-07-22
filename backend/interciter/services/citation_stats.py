"""Aggregate citation statistics — how a work or claim has been cited.

A derived, non-mutating read-side view (like :mod:`interciter.services.projection` and
:mod:`interciter.services.graph`): it rolls up the :class:`~interciter.models.
RelationAssertion` rows that *point at* a subject into tallies by stance, function,
resolution, and citing section, and returns the underlying citing statements.

This is InterCiter's answer to scite's "supporting / contrasting / mentioning" counts —
but with two deliberate differences the design mandates:

* function and stance are SEPARATE dimensions (not a single 3-way label); and
* abstention is explicit — a relation that commits to neither is counted apart, never
  silently bucketed as "mentioning".

Two subjects are supported:

* a **work** — every relation whose ``cited_work_id`` is the work (paper-level) *or*
  whose ``target_interpretation_id`` resolves to a claim that lives in the work
  (claim-level); and
* a **claim** — every relation whose ``target_interpretation_id`` is that interpretation.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import CitationStatement, CitationStats, CitationTallies, EvidenceRef


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


def _head_interpretation_id(session: Session, occurrence_id: str) -> str | None:
    """The current head interpretation of an occurrence (none lists it as a parent)."""
    interps = list(
        session.scalars(
            select(models.ClaimInterpretation).where(
                models.ClaimInterpretation.claim_occurrence_id == occurrence_id
            )
        )
    )
    if not interps:
        return None
    parents: set[str] = set()
    for interp in interps:
        parents.update(interp.parent_interpretation_ids or [])
    for interp in interps:
        if interp.interpretation_id not in parents:
            return interp.interpretation_id
    return interps[-1].interpretation_id


def _statement(
    session: Session, assertion: models.RelationAssertion
) -> CitationStatement:
    occurrence = session.get(models.ClaimOccurrence, assertion.citing_occurrence_id)
    passage = session.get(models.Passage, occurrence.passage_id) if occurrence else None
    evidence = _evidence_for_passage(session, passage) if passage else None
    return CitationStatement(
        assertion_id=assertion.assertion_id,
        citing_work_id=evidence.work_id if evidence else None,
        citing_claim_id=(
            _head_interpretation_id(session, occurrence.occurrence_id)
            if occurrence
            else None
        ),
        function=assertion.function,
        stance=assertion.stance,
        resolution=assertion.resolution,
        status=assertion.status,
        section=passage.section if passage else None,
        evidence=evidence,
    )


def _tallies(statements: list[CitationStatement]) -> CitationTallies:
    by_stance: Counter[str] = Counter()
    by_function: Counter[str] = Counter()
    by_resolution: Counter[str] = Counter()
    by_section: Counter[str] = Counter()
    abstained = 0
    for s in statements:
        if s.stance is not None:
            by_stance[s.stance.value] += 1
        if s.function is not None:
            by_function[s.function.value] += 1
        if s.stance is None and s.function is None:
            abstained += 1
        by_resolution[s.resolution.value] += 1
        by_section[s.section or "unspecified"] += 1
    return CitationTallies(
        total=len(statements),
        by_stance=dict(by_stance),
        by_function=dict(by_function),
        by_resolution=dict(by_resolution),
        by_section=dict(by_section),
        abstained=abstained,
    )


def _stats(
    session: Session,
    *,
    subject_type: str,
    subject_id: str,
    assertions: list[models.RelationAssertion],
) -> CitationStats:
    statements = [_statement(session, a) for a in assertions]
    statements.sort(key=lambda s: s.assertion_id)
    return CitationStats(
        subject_type=subject_type,
        subject_id=subject_id,
        tallies=_tallies(statements),
        statements=statements,
    )


def _interpretation_ids_for_work(session: Session, work_id: str) -> set[str]:
    stmt = (
        select(models.ClaimInterpretation.interpretation_id)
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
        .where(models.PaperVersion.work_id == work_id)
    )
    return set(session.scalars(stmt))


def citation_stats_for_work(session: Session, work_id: str) -> CitationStats:
    """Tallies of every relation that cites the work (paper-level or claim-level).

    Raises :class:`KeyError` if the work does not exist.
    """
    if session.get(models.PaperWork, work_id) is None:
        raise KeyError(work_id)

    conditions = [models.RelationAssertion.cited_work_id == work_id]
    interp_ids = _interpretation_ids_for_work(session, work_id)
    if interp_ids:
        conditions.append(
            models.RelationAssertion.target_interpretation_id.in_(interp_ids)
        )
    assertions = list(
        session.scalars(
            select(models.RelationAssertion).where(or_(*conditions))
        )
    )
    return _stats(
        session, subject_type="work", subject_id=work_id, assertions=assertions
    )


def citation_stats_for_claim(
    session: Session, interpretation_id: str
) -> CitationStats:
    """Tallies of every relation that resolved to this claim interpretation.

    Raises :class:`KeyError` if the interpretation does not exist.
    """
    if session.get(models.ClaimInterpretation, interpretation_id) is None:
        raise KeyError(interpretation_id)

    assertions = list(
        session.scalars(
            select(models.RelationAssertion).where(
                models.RelationAssertion.target_interpretation_id == interpretation_id
            )
        )
    )
    return _stats(
        session,
        subject_type="claim",
        subject_id=interpretation_id,
        assertions=assertions,
    )
