"""SQLAlchemy ORM — the immutable system of record.

These tables mirror the logical model in docs/data-model.md and schema/interciter.yaml.
They are append-only in *semantics*: nothing here is silently rewritten. Reads are
served by a derived projection (interciter.services.projection), never by mutating
these rows.

Portability: enums are stored as strings (``native_enum=False``) and list/dict fields
as JSON so the identical code runs on SQLite (local dev) and PostgreSQL (production).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from . import enums


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(py_enum) -> SAEnum:
    # Store enum values as portable VARCHARs rather than DB-native enum types.
    return SAEnum(py_enum, native_enum=False, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------------
# Bibliographic layer
# ---------------------------------------------------------------------------------


class PaperWork(Base):
    __tablename__ = "paper_work"

    work_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    pmid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    s2_corpus_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    availability_state: Mapped[enums.AvailabilityState] = mapped_column(
        _enum(enums.AvailabilityState),
        default=enums.AvailabilityState.metadata_stub,
    )

    versions: Mapped[list["PaperVersion"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class PaperVersion(Base):
    __tablename__ = "paper_version"

    version_id: Mapped[str] = mapped_column(String, primary_key=True)
    work_id: Mapped[str] = mapped_column(ForeignKey("paper_work.work_id"), index=True)
    manifestation: Mapped[enums.Manifestation] = mapped_column(_enum(enums.Manifestation))
    artifact_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    full_text_available: Mapped[bool] = mapped_column(Boolean, default=False)
    license_status: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_name: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String, nullable=True)
    parse_status: Mapped[enums.ParseStatus | None] = mapped_column(
        _enum(enums.ParseStatus), nullable=True
    )

    work: Mapped[PaperWork] = relationship(back_populates="versions")
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class Passage(Base):
    __tablename__ = "passage"

    passage_id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_version_id: Mapped[str] = mapped_column(
        ForeignKey("paper_version.version_id"), index=True
    )
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verbatim_text: Mapped[str] = mapped_column(Text)

    version: Mapped[PaperVersion] = relationship(back_populates="passages")


class CitationMention(Base):
    __tablename__ = "citation_mention"

    mention_id: Mapped[str] = mapped_column(String, primary_key=True)
    passage_id: Mapped[str] = mapped_column(ForeignKey("passage.passage_id"), index=True)
    marker_span: Mapped[str | None] = mapped_column(String, nullable=True)
    cited_work_id: Mapped[str | None] = mapped_column(
        ForeignKey("paper_work.work_id"), nullable=True, index=True
    )
    bibliographic_resolution_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    # Additive provenance/enrichment (e.g. Semantic Scholar intents + contexts). Weak
    # supervision only — never InterCiter's function/stance ontology.
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------------
# Extraction layer
# ---------------------------------------------------------------------------------


class ExtractionRun(Base):
    __tablename__ = "extraction_run"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String, nullable=True)
    code_revision: Mapped[str | None] = mapped_column(String, nullable=True)
    inference_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ClaimOccurrence(Base):
    __tablename__ = "claim_occurrence"

    occurrence_id: Mapped[str] = mapped_column(String, primary_key=True)
    passage_id: Mapped[str] = mapped_column(ForeignKey("passage.passage_id"), index=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrence_type: Mapped[enums.OccurrenceType] = mapped_column(
        _enum(enums.OccurrenceType)
    )
    extraction_run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_run.run_id"), index=True
    )

    passage: Mapped[Passage] = relationship()
    interpretations: Mapped[list["ClaimInterpretation"]] = relationship(
        back_populates="occurrence"
    )


class ClaimInterpretation(Base):
    __tablename__ = "claim_interpretation"

    interpretation_id: Mapped[str] = mapped_column(String, primary_key=True)
    claim_occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("claim_occurrence.occurrence_id"), index=True
    )
    normalized_text: Mapped[str] = mapped_column(Text)
    # Structured qualifiers are inlined as JSON (population, intervention, comparator,
    # outcome, dosage, time_horizon, effect_direction, effect_size, certainty, negated).
    qualifiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extraction_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("extraction_run.run_id"), nullable=True
    )
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Revision graph parents — a list, never a single superseded_by pointer.
    parent_interpretation_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    occurrence: Mapped[ClaimOccurrence] = relationship(back_populates="interpretations")


# ---------------------------------------------------------------------------------
# Equivalence layer — soft clustering
# ---------------------------------------------------------------------------------


class ClaimCluster(Base):
    __tablename__ = "claim_cluster"

    cluster_id: Mapped[str] = mapped_column(String, primary_key=True)
    clustering_method: Mapped[str | None] = mapped_column(String, nullable=True)
    threshold_version: Mapped[str | None] = mapped_column(String, nullable=True)

    memberships: Mapped[list["ClusterMembership"]] = relationship(
        back_populates="cluster"
    )


class ClusterMembership(Base):
    __tablename__ = "cluster_membership"

    membership_id: Mapped[str] = mapped_column(String, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("claim_cluster.cluster_id"), index=True
    )
    interpretation_id: Mapped[str] = mapped_column(
        ForeignKey("claim_interpretation.interpretation_id"), index=True
    )
    method: Mapped[enums.ClusteringMethod] = mapped_column(_enum(enums.ClusteringMethod))
    membership_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[enums.MembershipStatus] = mapped_column(
        _enum(enums.MembershipStatus), default=enums.MembershipStatus.active
    )
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cluster: Mapped[ClaimCluster] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------------
# Relationship layer — first-class assertions
# ---------------------------------------------------------------------------------


class RelationAssertion(Base):
    __tablename__ = "relation_assertion"

    assertion_id: Mapped[str] = mapped_column(String, primary_key=True)
    citing_occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("claim_occurrence.occurrence_id"), index=True
    )
    citation_mention_id: Mapped[str | None] = mapped_column(
        ForeignKey("citation_mention.mention_id"), nullable=True
    )
    evidence_passage_id: Mapped[str | None] = mapped_column(
        ForeignKey("passage.passage_id"), nullable=True
    )
    cited_work_id: Mapped[str | None] = mapped_column(
        ForeignKey("paper_work.work_id"), nullable=True, index=True
    )
    target_interpretation_id: Mapped[str | None] = mapped_column(
        ForeignKey("claim_interpretation.interpretation_id"), nullable=True
    )
    # Ranked candidate targets (each: {interpretation_id, score}) when unresolved.
    target_candidates: Mapped[list[dict]] = mapped_column(JSON, default=list)
    function: Mapped[enums.RelationFunction | None] = mapped_column(
        _enum(enums.RelationFunction), nullable=True
    )
    stance: Mapped[enums.RelationStance | None] = mapped_column(
        _enum(enums.RelationStance), nullable=True
    )
    scope: Mapped[enums.RelationScope | None] = mapped_column(
        _enum(enums.RelationScope), nullable=True
    )
    resolution: Mapped[enums.RelationResolution] = mapped_column(
        _enum(enums.RelationResolution), default=enums.RelationResolution.unresolved
    )
    # Two scores, deliberately separate (docs/scoring-and-review.md).
    target_link_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stance_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extraction_run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_run.run_id"), index=True
    )
    status: Mapped[enums.AssertionStatus] = mapped_column(
        _enum(enums.AssertionStatus), default=enums.AssertionStatus.proposed
    )


# ---------------------------------------------------------------------------------
# Review and assessment layer
# ---------------------------------------------------------------------------------


class ReviewDecision(Base):
    __tablename__ = "review_decision"

    review_id: Mapped[str] = mapped_column(String, primary_key=True)
    subject_type: Mapped[enums.ReviewSubjectType] = mapped_column(
        _enum(enums.ReviewSubjectType)
    )
    subject_id: Mapped[str] = mapped_column(String, index=True)
    reviewer_id: Mapped[str] = mapped_column(String)
    decision_dimension: Mapped[str] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Assessment(Base):
    __tablename__ = "assessment"

    assessment_id: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String, index=True)
    assessment_type: Mapped[str] = mapped_column(String)
    component_inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    algorithm_version: Mapped[str | None] = mapped_column(String, nullable=True)
    computed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------------
# Grounding — external entity normalization (derived, additive, non-mutating)
# ---------------------------------------------------------------------------------


class EntityGrounding(Base):
    __tablename__ = "entity_grounding"

    grounding_id: Mapped[str] = mapped_column(String, primary_key=True)
    interpretation_id: Mapped[str] = mapped_column(
        ForeignKey("claim_interpretation.interpretation_id"), index=True
    )
    grounding_role: Mapped[str | None] = mapped_column(String, nullable=True)
    grounded_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    grounded_curie: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    grounded_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    grounding_source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------------
# Jobs — first-class async work resources (docs/architecture.md, api.md)
# ---------------------------------------------------------------------------------


class Job(Base):
    __tablename__ = "job"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[enums.JobType] = mapped_column(_enum(enums.JobType))
    status: Mapped[enums.JobStatus] = mapped_column(
        _enum(enums.JobStatus), default=enums.JobStatus.queued
    )
    # Idempotency key so retried submissions don't double-ingest (api.md).
    idempotency_key: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    # First-class ownership: the user who submitted the work (docs/architecture.md).
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    paper_work_id: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------------
# Identity — minimal role-based auth + first-class ownership
# ---------------------------------------------------------------------------------


class User(Base):
    """A principal. Ownership is first-class from day one; the role layer stays minimal
    (``user`` / ``reviewer`` / ``admin``) per docs/architecture.md.
    """

    __tablename__ = "app_user"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    role: Mapped[enums.Role] = mapped_column(_enum(enums.Role), default=enums.Role.user)
    # Opaque bearer token. Stored hashed so a DB leak does not expose usable credentials.
    api_token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
