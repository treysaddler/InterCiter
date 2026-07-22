"""Network-graph exploration — papers, authors, citations, and claims.

Reads (the graph views) stay open like the rest of the read surface. On-demand
expansion writes to the store (new stub works + bibliographic edges), so it requires an
authenticated principal and — for cookie auth — a CSRF token, exactly like ingestion.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import models
from ...auth import Principal
from ...ingestion.robokop import RobokopError
from ...ingestion.semantic_scholar import S2Error
from ...schemas import ClaimExpandRequest, ClaimExpansion, GraphExpansion, GraphView
from ...services import graph
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.get("/graph/papers", response_model=GraphView)
def paper_graph(
    limit: int = graph.DEFAULT_PAPER_LIMIT,
    include_authors: bool = False,
    session: Session = Depends(db_session),
) -> GraphView:
    """A bounded overview of the citation network (US: explore papers/authors)."""
    return graph.build_paper_graph(
        session, limit=limit, include_authors=include_authors
    )


@router.get("/graph/papers/{work_id}", response_model=GraphView)
def paper_neighborhood(
    work_id: str,
    depth: int = 1,
    include_authors: bool = False,
    session: Session = Depends(db_session),
) -> GraphView:
    """The citation neighborhood centered on one paper, BFS to ``depth`` hops."""
    try:
        return graph.paper_neighborhood(
            session, work_id, depth=depth, include_authors=include_authors
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="paper not found") from exc


@router.post("/graph/papers/{work_id}/expand", response_model=GraphExpansion)
def expand_paper(
    work_id: str,
    limit: int = graph.DEFAULT_EXPAND_LIMIT,
    include_authors: bool = False,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> GraphExpansion:
    """Pull the paper's references from Semantic Scholar and persist them into the graph."""
    work = session.get(models.PaperWork, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="paper not found")
    try:
        return graph.expand_from_semantic_scholar(
            session, work, limit=limit, include_authors=include_authors
        )
    except S2Error as exc:
        raise HTTPException(status_code=502, detail=f"Semantic Scholar: {exc}") from exc


@router.get("/graph/claims", response_model=GraphView)
def claim_graph(
    limit: int = graph.DEFAULT_PAPER_LIMIT,
    session: Session = Depends(db_session),
) -> GraphView:
    """The in-corpus claim-relationship network (function/stance-tagged edges)."""
    return graph.claim_graph(session, limit=limit)


@router.post("/graph/claims/{interpretation_id}/expand-robokop", response_model=ClaimExpansion)
def expand_claim_robokop(
    interpretation_id: str,
    body: ClaimExpandRequest | None = None,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> ClaimExpansion:
    """Explore a claim in the ROBOKOP knowledge graph.

    Grounds the claim's entity qualifiers (or the explicit ``terms`` in the body) to
    canonical CURIEs and draws the background-knowledge edges between them, with
    knowledge-source provenance. Corroborating context, never a truth oracle.
    """
    interp = session.get(models.ClaimInterpretation, interpretation_id)
    if interp is None:
        raise HTTPException(status_code=404, detail="claim not found")
    extra = [(t.role, t.term) for t in (body.terms if body else [])]
    try:
        return graph.expand_claim_robokop(session, interp, extra_terms=extra)
    except RobokopError as exc:
        raise HTTPException(status_code=502, detail=f"ROBOKOP: {exc}") from exc
