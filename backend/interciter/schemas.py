"""Pydantic API schemas (request/response DTOs).

Two representation styles, matching the design (docs/architecture.md, api.md):

* **Composed, reader-friendly views** are the default read path — claim text plus a
  source snippet plus a provenance link — so a researcher never has to understand
  occurrence-vs-interpretation to read a result.
* **Audit views** expose the underlying immutable records behind explicit endpoints.

These are decoupled from the ORM on purpose; the ORM is the system of record, these
are the contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from . import enums


# ---------------------------------------------------------------------------------
# Ingestion / jobs
# ---------------------------------------------------------------------------------


class PaperSubmission(BaseModel):
    """Submit a paper by identifier or inline open-access JATS XML."""

    doi: str | None = None
    pmid: str | None = None
    xml: str | None = Field(default=None, description="Inline open-access JATS XML.")
    manifestation: enums.Manifestation = enums.Manifestation.published
    idempotency_key: str | None = Field(
        default=None,
        description="Retries with the same key return the same job (no double-ingest).",
    )


class JobView(BaseModel):
    job_id: str
    job_type: enums.JobType
    status: enums.JobStatus
    owner_id: str | None = None
    paper_work_id: str | None = None
    extraction_run_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------------
# Bibliographic
# ---------------------------------------------------------------------------------


class PaperVersionView(BaseModel):
    version_id: str
    manifestation: enums.Manifestation
    artifact_hash: str | None = None
    full_text_available: bool
    license_status: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    parse_status: enums.ParseStatus | None = None


class PaperView(BaseModel):
    work_id: str
    title: str | None = None
    authors: list[str] = []
    venue: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    s2_corpus_id: str | None = None
    availability_state: enums.AvailabilityState
    # Additive integrity flags (scite-parity WP5); null until an integrity source
    # has been consulted.
    is_retracted: bool | None = None
    integrity_notice: str | None = None


class PassageView(BaseModel):
    passage_id: str
    paper_version_id: str
    section: str | None = None
    paragraph: int | None = None
    sentence: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    verbatim_text: str


# ---------------------------------------------------------------------------------
# Claims — composed default view + audit views
# ---------------------------------------------------------------------------------


class EvidenceRef(BaseModel):
    """The provenance link every claim/relation response embeds."""

    passage_id: str
    paper_version_id: str
    work_id: str
    section: str | None = None
    verbatim_text: str
    char_start: int | None = None
    char_end: int | None = None


class ClaimView(BaseModel):
    """Composed, reader-friendly claim view (the projected read-side object).

    ``claim_id`` is the current interpretation head's id; the audit trail sits behind
    the ``occurrence_id`` / ``interpretation_id`` links.
    """

    claim_id: str
    normalized_text: str
    occurrence_id: str
    interpretation_id: str
    occurrence_type: enums.OccurrenceType
    qualifiers: dict[str, Any] | None = None
    work_id: str
    evidence: EvidenceRef


class ClaimOccurrenceView(BaseModel):
    occurrence_id: str
    passage_id: str
    span_start: int | None = None
    span_end: int | None = None
    occurrence_type: enums.OccurrenceType
    extraction_run_id: str


class ClaimInterpretationView(BaseModel):
    interpretation_id: str
    claim_occurrence_id: str
    normalized_text: str
    qualifiers: dict[str, Any] | None = None
    extraction_run_id: str | None = None
    author_id: str | None = None
    parent_interpretation_ids: list[str] = []
    created_by: str | None = None
    created_at: datetime


class ExtractionRunView(BaseModel):
    run_id: str
    model: str | None = None
    provider: str | None = None
    model_version: str | None = None
    prompt_template_version: str | None = None
    parser_version: str | None = None
    code_revision: str | None = None
    inference_parameters: dict[str, Any] | None = None
    timestamp: datetime


# ---------------------------------------------------------------------------------
# Relations & traversal
# ---------------------------------------------------------------------------------


class TargetCandidate(BaseModel):
    interpretation_id: str
    score: float


class RelationAssertionView(BaseModel):
    assertion_id: str
    citing_occurrence_id: str
    citation_mention_id: str | None = None
    evidence_passage_id: str | None = None
    cited_work_id: str | None = None
    target_interpretation_id: str | None = None
    target_candidates: list[TargetCandidate] = []
    function: enums.RelationFunction | None = None
    stance: enums.RelationStance | None = None
    scope: enums.RelationScope | None = None
    resolution: enums.RelationResolution
    target_link_score: float | None = None
    stance_distribution: dict[str, float] | None = None
    extraction_run_id: str
    status: enums.AssertionStatus


class TraceHop(BaseModel):
    """One resolved hop from a claim to its cited antecedent.

    ``paper_resolved`` hops are labeled as such and never presented as a claim-level
    continuation (api.md).
    """

    assertion_id: str
    function: enums.RelationFunction | None = None
    stance: enums.RelationStance | None = None
    resolution: enums.RelationResolution
    target_link_score: float | None = None
    target_claim: ClaimView | None = None
    target_work: PaperView | None = None
    evidence: EvidenceRef | None = None


class OneHopTrace(BaseModel):
    root_claim_id: str
    hops: list[TraceHop] = []
    truncated: bool = False
    note: str | None = None


# ---------------------------------------------------------------------------------
# Human-authored claims, revisions, review, clusters
# ---------------------------------------------------------------------------------


class HumanClaimCreate(BaseModel):
    normalized_text: str
    passage_id: str | None = Field(
        default=None,
        description="Attach to an existing occurrence's passage; a new occurrence is created.",
    )
    occurrence_id: str | None = Field(
        default=None,
        description="Attach an interpretation to an existing occurrence instead.",
    )
    occurrence_type: enums.OccurrenceType = enums.OccurrenceType.reported_result
    qualifiers: dict[str, Any] | None = None


class InterpretationRevision(BaseModel):
    normalized_text: str
    qualifiers: dict[str, Any] | None = None
    material: bool = Field(
        default=True,
        description="Material revisions mark dependent assertions stale_pending_review.",
    )


class RevisionResult(BaseModel):
    new_interpretation: ClaimInterpretationView
    parent_interpretation_id: str
    staled_assertion_ids: list[str] = []


class ReviewDecisionCreate(BaseModel):
    subject_type: enums.ReviewSubjectType
    subject_id: str
    decision_dimension: str
    label: str | None = None
    rationale: str | None = None


class ReviewDecisionView(BaseModel):
    review_id: str
    subject_type: enums.ReviewSubjectType
    subject_id: str
    reviewer_id: str
    decision_dimension: str
    label: str | None = None
    rationale: str | None = None
    timestamp: datetime


class ClusterMemberView(BaseModel):
    membership_id: str
    interpretation_id: str
    normalized_text: str
    method: enums.ClusteringMethod
    membership_confidence: float | None = None
    status: enums.MembershipStatus
    stance_in_context: enums.RelationStance | None = None


class ClusterView(BaseModel):
    cluster_id: str
    clustering_method: str | None = None
    threshold_version: str | None = None
    members: list[ClusterMemberView] = []
    conflicting_stances: bool = False


# ---------------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------------


class ScoreComponent(BaseModel):
    name: str
    value: float | None = None
    assessment_id: str | None = None
    algorithm_version: str | None = None
    inputs: dict[str, Any] | None = None


class ClaimScores(BaseModel):
    """Decomposed signals — never a blended scalar (docs/scoring-and-review.md)."""

    claim_id: str
    components: list[ScoreComponent] = []


# ---------------------------------------------------------------------------------
# Citation statistics — aggregate "how has this been cited" (scite-parity WP1)
# ---------------------------------------------------------------------------------


class CitationStatement(BaseModel):
    """One citing relation pointing at the subject, carrying its section facet.

    A "citation statement" is a :class:`RelationAssertion` that targets the subject —
    either a cited work (paper-level resolution) or a specific target claim (claim-level
    resolution). Function and stance are kept as SEPARATE dimensions; an abstaining
    relation leaves both null rather than collapsing to a single label.
    """

    assertion_id: str
    citing_work_id: str | None = None
    citing_claim_id: str | None = None
    function: enums.RelationFunction | None = None
    stance: enums.RelationStance | None = None
    resolution: enums.RelationResolution
    status: enums.AssertionStatus
    section: str | None = None
    evidence: EvidenceRef | None = None


class CitationTallies(BaseModel):
    """Roll-up counts by each dimension (the scite-style supporting/contrasting view).

    Stance and function stay separate — there is no blended 3-way label. ``abstained``
    counts statements that commit to neither a function nor a stance.
    """

    total: int = 0
    by_stance: dict[str, int] = Field(default_factory=dict)
    by_function: dict[str, int] = Field(default_factory=dict)
    by_resolution: dict[str, int] = Field(default_factory=dict)
    by_section: dict[str, int] = Field(default_factory=dict)
    abstained: int = 0


class CitationStats(BaseModel):
    """How a work or claim has been cited across the corpus (tallies + statements)."""

    subject_type: str = Field(description='"work" or "claim".')
    subject_id: str
    tallies: CitationTallies
    statements: list[CitationStatement] = Field(default_factory=list)


# ---------------------------------------------------------------------------------
# Paper reports — scite-style per-paper dashboard payload (scite-parity WP3, F4)
# ---------------------------------------------------------------------------------


class ReportTimelinePoint(BaseModel):
    """Citation activity bucketed by citing-work publication year."""

    year: int
    statement_count: int = 0
    citing_work_count: int = 0


class ReportConflictSummary(BaseModel):
    """Quick signal for conflicting stances in a paper's incoming citations."""

    has_conflicting_stances: bool = False
    supporting_statements: int = 0
    contradicting_statements: int = 0
    neutral_or_unclear_statements: int = 0
    conflicting_citing_work_count: int = 0


class ReportFacets(BaseModel):
    """Available filter values with counts over the unfiltered citation set."""

    section: dict[str, int] = Field(default_factory=dict)
    function: dict[str, int] = Field(default_factory=dict)
    stance: dict[str, int] = Field(default_factory=dict)
    resolution: dict[str, int] = Field(default_factory=dict)
    year: dict[str, int] = Field(default_factory=dict)


class ReportAppliedFilters(BaseModel):
    """Filters applied to the report statement list + tallies."""

    section: str | None = None
    function: str | None = None
    stance: str | None = None
    resolution: str | None = None
    min_year: int | None = None
    max_year: int | None = None


class PaperReport(BaseModel):
    """Derived per-paper citation report (tallies, timeline, conflicts, statements)."""

    work_id: str
    total_statements: int = 0
    filtered_statements: int = 0
    facets: ReportFacets = Field(default_factory=ReportFacets)
    applied_filters: ReportAppliedFilters = Field(default_factory=ReportAppliedFilters)
    tallies: CitationTallies = Field(default_factory=CitationTallies)
    timeline: list[ReportTimelinePoint] = Field(default_factory=list)
    conflict_summary: ReportConflictSummary = Field(default_factory=ReportConflictSummary)
    statements: list[CitationStatement] = Field(default_factory=list)


# ---------------------------------------------------------------------------------
# Full-text claim search (scite-parity WP2, F3)
# ---------------------------------------------------------------------------------


class SearchHit(BaseModel):
    """One claim that matched a full-text search, with its provenance and facets.

    The unit is the current interpretation *head* of a claim occurrence. ``function``,
    ``stance``, and ``resolution`` list the distinct values across the relations that
    cite from this claim (kept as SEPARATE dimensions, never a blended label).
    """

    claim_id: str
    normalized_text: str
    occurrence_id: str
    interpretation_id: str
    work_id: str
    paper_title: str | None = None
    year: int | None = None
    section: str | None = None
    function: list[str] = Field(default_factory=list)
    stance: list[str] = Field(default_factory=list)
    resolution: list[str] = Field(default_factory=list)
    evidence: EvidenceRef


class SearchFacets(BaseModel):
    """Available facet values (with counts) for the current text query.

    Counts are computed over the text/year-matched candidate set *before* the
    categorical facets are applied, so the reader always sees every option that a
    given query could narrow to.
    """

    section: dict[str, int] = Field(default_factory=dict)
    function: dict[str, int] = Field(default_factory=dict)
    stance: dict[str, int] = Field(default_factory=dict)
    resolution: dict[str, int] = Field(default_factory=dict)


class SearchResults(BaseModel):
    """A page of claim search results plus facet counts for the whole match set."""

    query: str
    total: int
    limit: int
    offset: int
    hits: list[SearchHit] = Field(default_factory=list)
    facets: SearchFacets = Field(default_factory=SearchFacets)


# ---------------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------------


class UserCreate(BaseModel):
    display_name: str
    role: enums.Role = enums.Role.user


class UserView(BaseModel):
    user_id: str
    display_name: str
    role: enums.Role
    is_active: bool = True
    created_at: datetime


class UserUpdate(BaseModel):
    """Partial account update — role and/or activation (admin)."""

    role: enums.Role | None = None
    is_active: bool | None = None


class UserCreated(UserView):
    """Returned once on creation — the only time the raw token is exposed."""

    api_token: str


class TokenRotated(UserView):
    """Returned once on rotation — the new raw token is exposed exactly once."""

    api_token: str


class CurrentUser(BaseModel):
    user_id: str
    display_name: str
    role: enums.Role


# ---------------------------------------------------------------------------------
# Browser session (BFF — docs/ui-design.md §11)
# ---------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Exchange a raw API token (sent once over TLS) for an HttpOnly session cookie."""

    api_token: str


class SessionInfo(BaseModel):
    """Login/session response. The CSRF token must accompany cookie-auth writes."""

    user_id: str
    display_name: str
    role: enums.Role
    csrf_token: str
    expires_at: datetime


# ---------------------------------------------------------------------------------
# Collections — curated user-owned sets of works (scite-parity WP4)
# ---------------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CollectionUpdate(BaseModel):
    """PATCH payload; an explicitly-null description clears the stored value."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CollectionMemberView(BaseModel):
    collection_membership_id: str
    work_id: str
    title: str | None = None
    doi: str | None = None
    pmid: str | None = None
    year: int | None = None
    added_at: datetime
    citation_tallies: CitationTallies | None = None
    # Additive integrity flags (scite-parity WP5 starter); null until an
    # integrity source has been consulted.
    is_retracted: bool | None = None
    integrity_notice: str | None = None


class CollectionView(BaseModel):
    collection_id: str
    owner_id: str
    name: str
    description: str | None = None
    member_count: int = 0
    is_watched: bool = False
    watch_snapshot_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CollectionDetailView(CollectionView):
    aggregate_citation_tallies: CitationTallies | None = None
    members: list[CollectionMemberView] = Field(default_factory=list)


class CollectionWatchRequest(BaseModel):
    """Toggle monitoring. Enabling (re)captures the new-citation baseline."""

    watch: bool


class CollectionMemberDelta(BaseModel):
    work_id: str
    title: str | None = None
    new_support: int = 0
    new_contradict: int = 0


class CollectionCitationDelta(BaseModel):
    """Newly observed support/contradict signals vs the last watch snapshot."""

    collection_id: str
    has_snapshot: bool = False
    snapshot_at: datetime | None = None
    new_support_total: int = 0
    new_contradict_total: int = 0
    members: list[CollectionMemberDelta] = Field(default_factory=list)


class CollectionBulkRemoveRequest(BaseModel):
    work_ids: list[str] = Field(min_length=1, max_length=500)


class CollectionBulkRemoveResult(BaseModel):
    collection_id: str
    removed_count: int = 0
    removed_work_ids: list[str] = Field(default_factory=list)


class CollectionAddMembersRequest(BaseModel):
    """Batch member intake by internal ids, identifiers, or CSV/plain-text blob."""

    work_ids: list[str] = Field(default_factory=list, max_length=500)
    dois: list[str] = Field(default_factory=list, max_length=500)
    pmids: list[str] = Field(default_factory=list, max_length=500)
    csv_text: str | None = Field(
        default=None,
        max_length=200_000,
        description=(
            "Optional newline/comma-separated identifiers; DOIs and PMIDs are "
            "auto-detected and merged with explicit arrays."
        ),
    )


class CollectionAddMembersResult(BaseModel):
    collection_id: str
    added_count: int = 0
    skipped_identifiers: list[str] = Field(default_factory=list)
    created_stub_work_ids: list[str] = Field(default_factory=list)
    members: list[CollectionMemberView] = Field(default_factory=list)


# ---------------------------------------------------------------------------------
# Saved maps — persisted citation-map seed sets + layout (litmaps-parity WP-L2)
# ---------------------------------------------------------------------------------


class MapMemberView(BaseModel):
    map_membership_id: str
    work_id: str
    title: str | None = None
    doi: str | None = None
    pmid: str | None = None
    year: int | None = None
    note: str | None = None
    position: dict[str, Any] | None = None
    added_at: datetime


class MapView(BaseModel):
    map_id: str
    owner_id: str
    name: str
    description: str | None = None
    layout_config: dict[str, Any] = Field(default_factory=dict)
    member_count: int = 0
    # Present only when the map has been shared; the owner uses it to build the link.
    share_token: str | None = None
    created_at: datetime
    updated_at: datetime


class MapDetailView(MapView):
    members: list[MapMemberView] = Field(default_factory=list)


class MapCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    layout_config: dict[str, Any] = Field(default_factory=dict)
    # Optional seed set of existing works to populate the map on creation.
    work_ids: list[str] = Field(default_factory=list, max_length=1000)


class MapUpdate(BaseModel):
    """PATCH payload; an explicitly-null description clears the stored value."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    layout_config: dict[str, Any] | None = None


class MapAddMembersRequest(BaseModel):
    work_ids: list[str] = Field(min_length=1, max_length=1000)


class MapMemberUpdate(BaseModel):
    """Annotate a map member; omitted fields are left unchanged."""

    note: str | None = Field(default=None, max_length=2000)
    position: dict[str, Any] | None = None


class MapShareView(BaseModel):
    """The capability token minted for a shared map (litmaps-parity WP-L4)."""

    map_id: str
    share_token: str


class SharedMapView(BaseModel):
    """Read-only projection of a shared map, reachable by token without auth.

    Deliberately excludes the owner id and any other identity so a shared link never
    leaks who created the map.
    """

    map_id: str
    name: str
    description: str | None = None
    layout_config: dict[str, Any] = Field(default_factory=dict)
    member_count: int = 0
    members: list[MapMemberView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------------
# Monitoring — saved searches + alerts (scite-parity WP8)
# ---------------------------------------------------------------------------------


class SearchQuery(BaseModel):
    """The persisted parameters of a saved claim search (mirrors search_claims)."""

    q: str = ""
    section: str | None = None
    function: str | None = None
    stance: str | None = None
    resolution: str | None = None
    min_year: int | None = None
    max_year: int | None = None


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: SearchQuery = Field(default_factory=SearchQuery)


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    query: SearchQuery | None = None


class SavedSearchView(BaseModel):
    saved_search_id: str
    owner_id: str
    name: str
    query: SearchQuery
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertView(BaseModel):
    alert_id: str
    source_type: str
    source_id: str
    alert_type: str
    work_id: str | None = None
    claim_id: str | None = None
    summary: str
    is_read: bool = False
    created_at: datetime


class AlertRunResult(BaseModel):
    """Outcome of running monitoring checks: newly created alerts."""

    created_count: int = 0
    alerts: list[AlertView] = Field(default_factory=list)


# ---------------------------------------------------------------------------------
# Network graph — papers/authors/citations (and, later, ROBOKOP claims)
# ---------------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A node in an exploration graph.

    ``type`` is an open discriminator (``paper``, ``author``, ``claim``, …) so the same
    envelope serves the citation network today and ROBOKOP claim graphs later. ``data``
    carries type-specific fields the UI may render without a second request.
    """

    id: str
    type: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed edge (``source`` → ``target``) with an open ``type`` discriminator."""

    id: str
    source: str
    target: str
    type: str
    label: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class GraphView(BaseModel):
    """A node/edge set for a network view, plus provenance about how it was built."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    center_id: str | None = Field(
        default=None, description="The focus node for a neighborhood view, if any."
    )
    truncated: bool = Field(
        default=False,
        description="True when a node/edge cap was hit and the view is partial.",
    )


class GraphExpansion(BaseModel):
    """Result of an on-demand Semantic Scholar expansion around a work."""

    work_id: str
    references_fetched: int = 0
    works_created: int = 0
    edges_created: int = 0
    skipped_reason: str | None = None
    graph: GraphView


class RobokopTerm(BaseModel):
    """An explicit ``(role, term)`` to ground when a claim's qualifiers are empty."""

    role: str
    term: str


class ClaimExpandRequest(BaseModel):
    """Optional body for ROBOKOP claim expansion.

    When the extractor has filled a claim's entity qualifiers they are grounded
    automatically; ``terms`` lets a caller supply entities explicitly (useful while the
    stub extractor abstains on qualifiers).
    """

    terms: list[RobokopTerm] = Field(default_factory=list)


class ClaimExpansion(BaseModel):
    """Result of expanding a claim's neighborhood via ROBOKOP grounding + KG edges."""

    interpretation_id: str
    grounded_terms: int = 0
    resolved_terms: int = 0
    corroborating_edges: int = 0
    graph: GraphView


# ---------------------------------------------------------------------------------
# Seed-based discovery — ranked connected papers (litmaps-parity WP-L1)
# ---------------------------------------------------------------------------------


class DiscoveryRequest(BaseModel):
    """Ask for the papers most connected to a set of seed works."""

    seed_work_ids: list[str] = Field(min_length=1)
    limit: int = Field(default=25, ge=1, le=100)
    min_year: int | None = Field(
        default=None, description="Drop candidates published before this year (when known)."
    )


class DiscoveryCandidate(BaseModel):
    """A candidate paper ranked by how many seeds connect to it.

    ``work_id`` is set when the candidate already exists in the corpus (so the UI can
    deep-link it); otherwise ``external_id`` carries a Semantic Scholar identifier the
    user could ingest. Nothing is persisted by discovery — these are suggestions.
    """

    work_id: str | None = None
    external_id: str | None = None
    title: str | None = None
    year: int | None = None
    connection_score: int = Field(
        default=0, description="Number of seed works that reference this candidate."
    )
    supporting_seed_ids: list[str] = Field(default_factory=list)
    is_influential: bool = False
    in_corpus: bool = False


class DiscoveryResult(BaseModel):
    """Ranked discovery candidates plus which seeds could be resolved."""

    seed_work_ids: list[str] = Field(default_factory=list)
    candidates: list[DiscoveryCandidate] = Field(default_factory=list)
    seeds_resolved: int = Field(
        default=0, description="Seeds that had a DOI/PMID/corpusId to query."
    )
    skipped_seed_ids: list[str] = Field(default_factory=list)
