"""Job orchestration — first-class async work resources.

The design's external notification model for the MVP is **polling on a job resource**
(webhooks are phase 2 on the same abstraction). Work runs inline here for simplicity,
but the job lifecycle (``queued`` → ``running`` → ``succeeded`` / ``failed``) and the
idempotency-key contract are modeled exactly as the API promises, so swapping in a real
worker queue later touches only this module.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..enums import AvailabilityState, JobStatus, JobType
from ..ids import new_id
from ..ingestion.parser import XMLParseError
from ..ingestion.pipeline import ingest_paper
from ..schemas import PaperSubmission


class SubmissionError(ValueError):
    """Raised for a malformed or oversized submission (a 4xx, not a job failure)."""


def get_job(session: Session, job_id: str) -> models.Job | None:
    return session.get(models.Job, job_id)


def submit_ingest(
    session: Session,
    submission: PaperSubmission,
    settings: Settings | None = None,
    owner_id: str | None = None,
) -> models.Job:
    settings = settings or get_settings()

    # Idempotency: a retried submission with the same key returns the same job.
    if submission.idempotency_key:
        existing = session.scalar(
            select(models.Job).where(
                models.Job.idempotency_key == submission.idempotency_key
            )
        )
        if existing is not None:
            return existing

    if not submission.xml and not (submission.doi or submission.pmid):
        raise SubmissionError("provide inline xml, or a doi/pmid identifier")

    if submission.xml is not None:
        size = len(submission.xml.encode("utf-8"))
        if size > settings.max_upload_bytes:
            raise SubmissionError(
                f"document exceeds max_upload_bytes ({size} > {settings.max_upload_bytes})"
            )

    job = models.Job(
        job_id=new_id("Job"),
        job_type=JobType.ingest,
        status=JobStatus.queued,
        idempotency_key=submission.idempotency_key,
        owner_id=owner_id,
    )
    session.add(job)
    session.commit()

    _run_ingest(session, job, submission, settings)
    return job


def _run_ingest(
    session: Session,
    job: models.Job,
    submission: PaperSubmission,
    settings: Settings,
) -> None:
    job.status = JobStatus.running
    session.commit()

    try:
        if submission.xml is None:
            # No full text available in the MVP (no external hydration in the stub).
            work = _register_metadata_stub(session, submission)
            job.paper_work_id = work.work_id
            job.result = {
                "work_id": work.work_id,
                "availability_state": AvailabilityState.full_text_unavailable.value,
                "note": "Registered as a metadata stub; full-text hydration is deferred.",
            }
            job.status = JobStatus.succeeded
            session.commit()
            return

        result = ingest_paper(
            session,
            xml=submission.xml,
            manifestation=submission.manifestation,
            doi=submission.doi,
            pmid=submission.pmid,
            settings=settings,
        )
        job.paper_work_id = result.work_id
        job.extraction_run_id = result.run_id
        job.result = {
            "work_id": result.work_id,
            "version_id": result.version_id,
            "run_id": result.run_id,
            "availability_state": result.availability_state.value,
            "passages": result.passages,
            "citation_mentions": result.citation_mentions,
            "occurrences": result.occurrences,
            "interpretations": result.interpretations,
            "relation_assertions": result.relation_assertions,
            "claim_resolved": result.claim_resolved,
            "paper_resolved": result.paper_resolved,
            "unresolved": result.unresolved,
        }
        job.status = JobStatus.succeeded
        session.commit()
    except XMLParseError as exc:
        session.rollback()
        _fail(session, job.job_id, f"parse error: {exc}")
    except Exception as exc:  # noqa: BLE001 - record any failure on the job
        session.rollback()
        _fail(session, job.job_id, f"ingestion failed: {exc}")


def _fail(session: Session, job_id: str, message: str) -> None:
    job = session.get(models.Job, job_id)
    if job is None:
        return
    job.status = JobStatus.failed
    job.error = message
    session.commit()


def _register_metadata_stub(
    session: Session, submission: PaperSubmission
) -> models.PaperWork:
    existing = None
    if submission.doi:
        existing = session.scalar(
            select(models.PaperWork).where(models.PaperWork.doi == submission.doi)
        )
    if existing is None and submission.pmid:
        existing = session.scalar(
            select(models.PaperWork).where(models.PaperWork.pmid == submission.pmid)
        )
    if existing is not None:
        return existing
    work = models.PaperWork(
        work_id=new_id("PaperWork"),
        doi=submission.doi,
        pmid=submission.pmid,
        availability_state=AvailabilityState.full_text_unavailable,
    )
    session.add(work)
    session.commit()
    return work
