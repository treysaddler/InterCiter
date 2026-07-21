"""Controlled vocabularies.

These mirror the ``enums`` block of the LinkML schema (schema/interciter.yaml) so the
application layer speaks exactly the same vocabulary as the logical data model. They
are plain ``str`` enums so values serialize directly in JSON and SQL.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class Manifestation(StrEnum):
    preprint = "preprint"
    published = "published"
    correction = "correction"
    retraction_notice = "retraction_notice"


class ParseStatus(StrEnum):
    parsed = "parsed"
    partial = "partial"
    failed = "failed"


class AvailabilityState(StrEnum):
    full_text_extracted = "full_text_extracted"
    full_text_unavailable = "full_text_unavailable"
    metadata_stub = "metadata_stub"
    hydration_queued = "hydration_queued"
    ingestion_failed = "ingestion_failed"


class OccurrenceType(StrEnum):
    reported_result = "reported_result"
    background_assertion = "background_assertion"
    method_description = "method_description"
    hypothesis = "hypothesis"
    other = "other"


class EffectDirection(StrEnum):
    increase = "increase"
    decrease = "decrease"
    no_effect = "no_effect"
    mixed = "mixed"
    unclear = "unclear"


class Certainty(StrEnum):
    definite = "definite"
    probable = "probable"
    possible = "possible"
    speculative = "speculative"


class ClusteringMethod(StrEnum):
    automated = "automated"
    human = "human"


class MembershipStatus(StrEnum):
    active = "active"
    removed = "removed"


class RelationFunction(StrEnum):
    background = "background"
    method = "method"
    direct_evidence = "direct_evidence"
    comparison = "comparison"
    other = "other"


class RelationStance(StrEnum):
    support = "support"
    contradict = "contradict"
    neutral = "neutral"
    unclear = "unclear"


class RelationScope(StrEnum):
    whole_claim = "whole_claim"
    partial_claim = "partial_claim"
    paper_level_only = "paper_level_only"


class RelationResolution(StrEnum):
    claim_resolved = "claim_resolved"
    paper_resolved = "paper_resolved"
    unresolved = "unresolved"


class AssertionStatus(StrEnum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    unresolved = "unresolved"
    stale_pending_review = "stale_pending_review"


class ReviewSubjectType(StrEnum):
    claim_occurrence = "claim_occurrence"
    claim_interpretation = "claim_interpretation"
    relation_assertion = "relation_assertion"
    cluster_membership = "cluster_membership"


class JobType(StrEnum):
    ingest = "ingest"
    extract = "extract"
    hydrate = "hydrate"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Role(StrEnum):
    """Minimal role set (docs/architecture.md — Auth). ``admin`` implies all rights."""

    user = "user"
    reviewer = "reviewer"
    admin = "admin"
