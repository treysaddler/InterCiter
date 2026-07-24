"""Cohorts — the shared saved-set base (unifies Collection/Map membership).

A *cohort* is an interchangeable set of works any analysis screen can accept. This
router exposes the one place a saved cohort *source* (a collection or a map) resolves
to a display name + member count, so every cohort-aware surface (the analytics banner
today, future screens tomorrow) resolves saved sets the same way. The heavy analysis
endpoints still resolve cohorts to work ids server-side via
:func:`interciter.services.cohort.resolve_cohort`.

Reads stay open, but a saved set is owner-private: resolving one requires the caller
to be its owner (else 401 when anonymous, 404 when owned by someone else).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...auth import Principal
from ...schemas import CohortView
from ...services import cohort
from ...services.projection import NotFound
from ..deps import db_session
from ..security import get_optional_principal

router = APIRouter()


@router.get("/cohorts/resolve", response_model=CohortView)
def resolve_cohort_source(
    collection: str | None = Query(
        None, description="Resolve a saved collection's cohort (owner-scoped)."
    ),
    map_id: str | None = Query(
        None, alias="map", description="Resolve a saved map's cohort (owner-scoped)."
    ),
    session: Session = Depends(db_session),
    principal: Principal | None = Depends(get_optional_principal),
) -> CohortView:
    """Describe a saved cohort source: its kind, name, and member count."""
    try:
        source = cohort.resolve_source(
            session, collection=collection, map_id=map_id, principal=principal
        )
    except cohort.AmbiguousCohort as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except cohort.CohortAuthRequired as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:  # nothing specified
        raise HTTPException(
            status_code=400, detail="specify a collection or map to resolve"
        ) from exc
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CohortView(
        source_type=source.kind,
        source_id=source.source_id,
        name=source.name,
        member_count=source.member_count,
    )
