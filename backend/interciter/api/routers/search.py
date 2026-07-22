"""Full-text claim search (scite-parity WP2, F3).

Search over the verbatim claim / citation-statement text, not just title/abstract.
Reads stay open (no auth) like the rest of the read surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas import SearchResults
from ...services import search
from ..deps import db_session

router = APIRouter()


@router.get("/search/claims", response_model=SearchResults)
def search_claims(
    q: str = Query("", description="Keyword matched against claim + source passage text."),
    section: str | None = Query(None, description="Filter to a source section."),
    function: str | None = Query(None, description="Relation function facet."),
    stance: str | None = Query(None, description="Relation stance facet."),
    resolution: str | None = Query(None, description="Relation resolution facet."),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(db_session),
) -> SearchResults:
    """Search claims by keyword with faceted filters (US: find claims across the corpus)."""
    return search.search_claims(
        session,
        q=q,
        section=section,
        function=function,
        stance=stance,
        resolution=resolution,
        min_year=min_year,
        max_year=max_year,
        limit=limit,
        offset=offset,
    )
