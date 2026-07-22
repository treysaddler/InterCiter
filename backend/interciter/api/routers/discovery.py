"""Seed-based discovery — ranked papers connected to a set of seed works.

Discovery performs a network read against Semantic Scholar (fetching the seeds'
references), so — like graph expansion — it requires an authenticated principal and, for
cookie auth, a CSRF token. It persists nothing; the response is a suggestion list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import Principal
from ...ingestion.semantic_scholar import S2Error
from ...schemas import DiscoveryRequest, DiscoveryResult
from ...services import discovery
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.post("/discovery/seeds", response_model=DiscoveryResult)
def discover_from_seeds(
    body: DiscoveryRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> DiscoveryResult:
    """Rank the papers most connected to the seed works (US: dive deeper / discover)."""
    try:
        return discovery.discover_from_seeds(
            session,
            body.seed_work_ids,
            limit=body.limit,
            min_year=body.min_year,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"seed work not found: {exc}"
        ) from exc
    except S2Error as exc:
        raise HTTPException(status_code=502, detail=f"Semantic Scholar: {exc}") from exc
