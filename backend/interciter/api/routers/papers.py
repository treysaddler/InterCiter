"""Ingestion, jobs, papers, versions, and extraction runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models
from ...auth import Principal
from ...schemas import (
    CitationStats,
    ExtractionRunView,
    JobView,
    PaperLookupRequest,
    PaperLookupResult,
    PaperReport,
    PaperSubmission,
    PaperVersionView,
    PaperView,
)
from ...services import citation_stats, jobs, lookup, report
from ...services.jobs import SubmissionError
from ...services.lookup import LookupError
from ...services.projection import list_papers as _list_papers, paper_view
from ..deps import db_session
from ..security import require_user

router = APIRouter()


def _job_view(job: models.Job) -> JobView:
    return JobView(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        owner_id=job.owner_id,
        paper_work_id=job.paper_work_id,
        extraction_run_id=job.extraction_run_id,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/papers", response_model=JobView, status_code=status.HTTP_202_ACCEPTED)
def submit_paper(
    submission: PaperSubmission,
    response: Response,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> JobView:
    """Submit by DOI/PMID or inline open-access XML. Returns a job resource to poll."""
    try:
        job = jobs.submit_ingest(session, submission, owner_id=principal.user_id)
    except SubmissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.headers["Location"] = f"/v1/jobs/{job.job_id}"
    return _job_view(job)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, session: Session = Depends(db_session)) -> JobView:
    job = jobs.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_view(job)


@router.post("/papers/lookup", response_model=PaperLookupResult)
def lookup_paper(
    request: PaperLookupRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> PaperLookupResult:
    """Fetch a paper from Semantic Scholar by external id and cache it locally.

    Read-through cache: a paper we already hold is returned straight from the database;
    otherwise it is fetched from the Academic Graph, persisted (metadata, abstract,
    TLDR, and — optionally — its references as citation edges to stub works), and
    returned. Browsing this way organically bootstraps the corpus. Requires a signed-in
    user because it triggers outbound network calls.
    """
    try:
        res = lookup.fetch_and_cache_paper(
            session, request.external_id, with_references=request.with_references
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    work = session.get(models.PaperWork, res.work_id)
    return PaperLookupResult(
        paper=paper_view(work),
        cache_hit=res.cache_hit,
        created=res.created,
        fields_filled=res.fields_filled,
        stubs_created=res.stubs_created,
        edges_created=res.edges_created,
    )


@router.get("/papers/{work_id}", response_model=PaperView)
def get_paper(work_id: str, session: Session = Depends(db_session)) -> PaperView:
    work = session.get(models.PaperWork, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="paper not found")
    return paper_view(work)


@router.get("/papers", response_model=list[PaperView])
def list_papers(
    limit: int = 50, offset: int = 0, session: Session = Depends(db_session)
) -> list[PaperView]:
    """List ingested papers (the reader's entry point, US-1.2). Reads stay open."""
    return _list_papers(session, limit=max(1, min(limit, 200)), offset=max(0, offset))


@router.get("/papers/{work_id}/citation-stats", response_model=CitationStats)
def get_paper_citation_stats(
    work_id: str, session: Session = Depends(db_session)
) -> CitationStats:
    """How the paper has been cited: stance/function/section tallies + statements."""
    try:
        return citation_stats.citation_stats_for_work(session, work_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="paper not found") from exc


@router.get("/papers/{work_id}/report", response_model=PaperReport)
def get_paper_report(
    work_id: str,
    section: str | None = Query(None, description="Filter to a source section."),
    function: str | None = Query(None, description="Filter to one relation function."),
    stance: str | None = Query(None, description="Filter to one relation stance."),
    resolution: str | None = Query(None, description="Filter to one resolution state."),
    min_year: int | None = Query(None, description="Earliest citing-work year."),
    max_year: int | None = Query(None, description="Latest citing-work year."),
    session: Session = Depends(db_session),
) -> PaperReport:
    """Scite-style per-paper report: tallies, timeline, conflicts, and statements."""
    try:
        return report.paper_report_for_work(
            session,
            work_id,
            section=section,
            function=function,
            stance=stance,
            resolution=resolution,
            min_year=min_year,
            max_year=max_year,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="paper not found") from exc


@router.get("/papers/{work_id}/versions", response_model=list[PaperVersionView])
def get_versions(
    work_id: str, session: Session = Depends(db_session)
) -> list[PaperVersionView]:
    if session.get(models.PaperWork, work_id) is None:
        raise HTTPException(status_code=404, detail="paper not found")
    versions = session.scalars(
        select(models.PaperVersion).where(models.PaperVersion.work_id == work_id)
    )
    return [
        PaperVersionView(
            version_id=v.version_id,
            manifestation=v.manifestation,
            artifact_hash=v.artifact_hash,
            full_text_available=v.full_text_available,
            license_status=v.license_status,
            parser_name=v.parser_name,
            parser_version=v.parser_version,
            parse_status=v.parse_status,
        )
        for v in versions
    ]


@router.get("/extraction-runs/{run_id}", response_model=ExtractionRunView)
def get_extraction_run(
    run_id: str, session: Session = Depends(db_session)
) -> ExtractionRunView:
    run = session.get(models.ExtractionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="extraction run not found")
    return ExtractionRunView(
        run_id=run.run_id,
        model=run.model,
        provider=run.provider,
        model_version=run.model_version,
        prompt_template_version=run.prompt_template_version,
        parser_version=run.parser_version,
        code_revision=run.code_revision,
        inference_parameters=run.inference_parameters,
        timestamp=run.timestamp,
    )
