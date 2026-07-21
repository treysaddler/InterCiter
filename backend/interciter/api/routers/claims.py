"""Claims, evidence, occurrences, interpretations, revisions, and scores."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import models
from ...auth import NotAuthorized, Principal
from ...schemas import (
    ClaimInterpretationView,
    ClaimOccurrenceView,
    ClaimScores,
    ClaimView,
    HumanClaimCreate,
    InterpretationRevision,
    PassageView,
    RevisionResult,
)
from ...services import projection, review
from ...services.projection import NotFound
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.get("/claims/{claim_id}", response_model=ClaimView)
def get_claim(claim_id: str, session: Session = Depends(db_session)) -> ClaimView:
    try:
        return projection.get_claim(session, claim_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/papers/{work_id}/claims", response_model=list[ClaimView])
def get_paper_claims(
    work_id: str, session: Session = Depends(db_session)
) -> list[ClaimView]:
    if session.get(models.PaperWork, work_id) is None:
        raise HTTPException(status_code=404, detail="paper not found")
    return projection.claims_for_paper(session, work_id)


@router.post("/claims", response_model=ClaimInterpretationView, status_code=201)
def create_claim(
    payload: HumanClaimCreate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> ClaimInterpretationView:
    try:
        return review.create_human_claim(session, payload, principal)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/claim-occurrences/{occurrence_id}", response_model=ClaimOccurrenceView)
def get_occurrence(
    occurrence_id: str, session: Session = Depends(db_session)
) -> ClaimOccurrenceView:
    occ = session.get(models.ClaimOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="occurrence not found")
    return ClaimOccurrenceView(
        occurrence_id=occ.occurrence_id,
        passage_id=occ.passage_id,
        span_start=occ.span_start,
        span_end=occ.span_end,
        occurrence_type=occ.occurrence_type,
        extraction_run_id=occ.extraction_run_id,
    )


@router.get(
    "/claim-interpretations/{interpretation_id}",
    response_model=ClaimInterpretationView,
)
def get_interpretation(
    interpretation_id: str, session: Session = Depends(db_session)
) -> ClaimInterpretationView:
    interp = session.get(models.ClaimInterpretation, interpretation_id)
    if interp is None:
        raise HTTPException(status_code=404, detail="interpretation not found")
    return ClaimInterpretationView(
        interpretation_id=interp.interpretation_id,
        claim_occurrence_id=interp.claim_occurrence_id,
        normalized_text=interp.normalized_text,
        qualifiers=interp.qualifiers,
        extraction_run_id=interp.extraction_run_id,
        author_id=interp.author_id,
        parent_interpretation_ids=interp.parent_interpretation_ids or [],
        created_by=interp.created_by,
        created_at=interp.created_at,
    )


@router.post(
    "/claim-interpretations/{interpretation_id}/revisions",
    response_model=RevisionResult,
    status_code=201,
)
def revise_interpretation(
    interpretation_id: str,
    payload: InterpretationRevision,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> RevisionResult:
    try:
        return review.revise_interpretation(session, interpretation_id, payload, principal)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/passages/{passage_id}", response_model=PassageView)
def get_passage(passage_id: str, session: Session = Depends(db_session)) -> PassageView:
    passage = session.get(models.Passage, passage_id)
    if passage is None:
        raise HTTPException(status_code=404, detail="passage not found")
    return PassageView(
        passage_id=passage.passage_id,
        paper_version_id=passage.paper_version_id,
        section=passage.section,
        paragraph=passage.paragraph,
        sentence=passage.sentence,
        char_start=passage.char_start,
        char_end=passage.char_end,
        verbatim_text=passage.verbatim_text,
    )


@router.get("/claims/{claim_id}/scores", response_model=ClaimScores)
def get_scores(claim_id: str, session: Session = Depends(db_session)) -> ClaimScores:
    try:
        return projection.claim_scores(session, claim_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
