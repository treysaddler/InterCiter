"""Corpus bibliometrics — descriptive "Main Information" analytics (WP-B1).

Reads stay open (no auth), like the rest of the read surface. The cohort is an
optional repeatable ``work_ids`` query parameter (else the whole corpus), narrowed by
optional publication-year bounds.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas import (
    AuthorMetrics,
    BibliometricsSummary,
    CountryMetrics,
    SourceMetrics,
)
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


@router.get("/bibliometrics/authors", response_model=AuthorMetrics)
def bibliometrics_authors(
    work_ids: list[str] | None = Query(
        None, description="Optional cohort of work ids; omit for the whole corpus."
    ),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top authors."),
    session: Session = Depends(db_session),
) -> AuthorMetrics:
    """Author analytics: productivity, h-index, and the Lotka-law distribution."""
    return bibliometrics.author_metrics(
        session,
        work_ids=work_ids,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )


@router.get("/bibliometrics/sources", response_model=SourceMetrics)
def bibliometrics_sources(
    work_ids: list[str] | None = Query(
        None, description="Optional cohort of work ids; omit for the whole corpus."
    ),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top sources."),
    session: Session = Depends(db_session),
) -> SourceMetrics:
    """Source analytics: productivity, h-index impact, and Bradford's-law zones."""
    return bibliometrics.source_metrics(
        session,
        work_ids=work_ids,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )


@router.get("/bibliometrics/countries", response_model=CountryMetrics)
def bibliometrics_countries(
    work_ids: list[str] | None = Query(
        None, description="Optional cohort of work ids; omit for the whole corpus."
    ),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top countries."),
    session: Session = Depends(db_session),
) -> CountryMetrics:
    """Country analytics: production + single/multi-country collaboration (SCP/MCP)."""
    return bibliometrics.country_metrics(
        session,
        work_ids=work_ids,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )
