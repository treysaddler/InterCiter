"""Corpus bibliometrics — descriptive "Main Information" analytics (WP-B1).

Reads stay open (no auth), like the rest of the read surface. The cohort is an
optional repeatable ``work_ids`` query parameter (else the whole corpus), narrowed by
optional publication-year bounds.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas import BibliometricsSummary
from ...services import bibliometrics
from ..deps import db_session

router = APIRouter()


@router.get("/bibliometrics/summary", response_model=BibliometricsSummary)
def bibliometrics_summary(
    work_ids: list[str] | None = Query(
        None, description="Optional cohort of work ids; omit for the whole corpus."
    ),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top authors/sources/documents."),
    session: Session = Depends(db_session),
) -> BibliometricsSummary:
    """Corpus descriptive rollup (US: see a corpus's Main Information at a glance)."""
    return bibliometrics.corpus_summary(
        session,
        work_ids=work_ids,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )
