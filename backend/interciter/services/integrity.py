"""Integrity enrichment — retraction / editorial-notice flags (scite-parity WP5).

Non-destructive enrichment that flags retracted or noticed works from an external
integrity source (Crossref first, via its Retraction Watch integration). This mirrors
the S2 backfill philosophy: it only writes the additive ``is_retracted`` /
``integrity_notice`` columns on ``PaperWork`` and never touches any scientific assertion,
claim, occurrence, relation, or cluster.

Coverage caveat: Crossref surfaces editorial updates through a work's ``update-to`` block,
which depends on publishers depositing the linkage. Absence of a flag therefore means
"no integrity signal found", not a guarantee of integrity.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..ingestion import crossref

# Crossref ``update-to`` types (lowercased) that mark a work as retracted/withdrawn.
RETRACTION_TYPES = frozenset({"retraction", "removal", "withdrawal"})
# Types that are integrity notices but not full retractions.
NOTICE_TYPES = frozenset(
    {
        "expression_of_concern",
        "concern",
        "correction",
        "corrigendum",
        "erratum",
        "addendum",
        "clarification",
        "partial_retraction",
        "new_edition",
        "new_version",
    }
)


@dataclass
class IntegrityResult:
    work_id: str
    doi: str | None = None
    checked: bool = False
    is_retracted: bool | None = None
    integrity_notice: str | None = None
    changed: bool = False
    skipped_reason: str | None = None


def integrity_from_message(message: dict) -> tuple[bool, str | None]:
    """Interpret a Crossref ``message`` into ``(is_retracted, notice_label)``.

    Reads the ``update-to`` block (editorial updates linked to this DOI) and, as a
    fallback, a ``RETRACTED``-prefixed title. Retraction/withdrawal types set the
    retracted flag; other editorial types populate the notice label.
    """
    is_retracted = False
    notice: str | None = None

    for entry in message.get("update-to") or []:
        etype = (entry.get("type") or "").strip().lower()
        label = entry.get("label") or entry.get("type")
        if etype in RETRACTION_TYPES:
            is_retracted = True
            notice = notice or label
        elif etype in NOTICE_TYPES:
            notice = notice or label

    # Fallback: many retracted articles carry a "RETRACTED:" title prefix even when the
    # structured linkage is missing.
    if not is_retracted:
        for title in message.get("title") or []:
            if isinstance(title, str) and title.strip().lower().startswith("retracted"):
                is_retracted = True
                notice = notice or "Retracted"
                break

    return is_retracted, notice


def check_work(
    session: Session,
    work: models.PaperWork,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
    client=crossref,
) -> IntegrityResult:
    """Consult the integrity source for one work and write flags additively.

    Requires a DOI (the only identifier Crossref keys on here). Does not commit — the
    caller owns the session. Once consulted, ``is_retracted`` is set to a definite
    ``True``/``False`` so an unchecked ``None`` is distinguishable from "checked, clean".
    """
    settings = settings or get_settings()
    result = IntegrityResult(work_id=work.work_id, doi=work.doi)

    if not work.doi:
        result.skipped_reason = "no DOI to resolve"
        return result

    message = client.get_work(work.doi, settings=settings, use_cache=use_cache)
    result.checked = True
    if message is None:
        result.skipped_reason = "no Crossref record"
        return result

    is_retracted, notice = integrity_from_message(message)
    if work.is_retracted != is_retracted or work.integrity_notice != notice:
        result.changed = True
    work.is_retracted = is_retracted
    work.integrity_notice = notice
    result.is_retracted = is_retracted
    result.integrity_notice = notice
    return result


def check_all(
    session: Session,
    *,
    limit: int | None = None,
    only_unchecked: bool = False,
    settings: Settings | None = None,
    use_cache: bool = True,
    client=crossref,
) -> list[IntegrityResult]:
    """Check every work with a DOI (optionally only those not yet checked).

    Commits once at the end.
    """
    settings = settings or get_settings()
    stmt = select(models.PaperWork).where(models.PaperWork.doi.is_not(None))
    if only_unchecked:
        stmt = stmt.where(models.PaperWork.is_retracted.is_(None))
    if limit is not None:
        stmt = stmt.limit(limit)

    results = [
        check_work(session, work, settings=settings, use_cache=use_cache, client=client)
        for work in session.scalars(stmt)
    ]
    session.commit()
    return results
