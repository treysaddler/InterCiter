/**
 * Hand-written subset of the `/v1` response DTOs, mirroring
 * backend/interciter/schemas.py.
 *
 * TODO: replace this file with a client generated from FastAPI's OpenAPI schema
 * (docs/ui-design.md §3, §10). Kept minimal on purpose — only what the skeleton
 * screens reference today.
 */

export interface EvidenceRef {
  passage_id: string
  paper_version_id: string
  work_id: string
  section: string | null
  verbatim_text: string
  char_start: number | null
  char_end: number | null
}

export interface PaperView {
  work_id: string
  title: string | null
  authors: string[]
  venue: string | null
  year: number | null
  doi: string | null
  pmid: string | null
  s2_corpus_id: string | null
  availability_state: string
  is_retracted: boolean | null
  integrity_notice: string | null
}

export interface ClaimView {
  claim_id: string
  normalized_text: string
  occurrence_id: string
  interpretation_id: string
  occurrence_type: string
  qualifiers: Record<string, unknown> | null
  work_id: string
  evidence: EvidenceRef
}

export interface ScoreComponent {
  name: string
  value: number | null
  assessment_id: string | null
  algorithm_version: string | null
  inputs: Record<string, unknown> | null
}

export interface JobView {
  job_id: string
  job_type: string
  status: string
  owner_id: string | null
  paper_work_id: string | null
  extraction_run_id: string | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface UserView {
  user_id: string
  display_name: string
  role: string
  is_active: boolean
  created_at: string
}

export interface UserWithToken extends UserView {
  api_token: string
}

export interface SessionInfo {
  user_id: string
  display_name: string
  role: string
  csrf_token: string
  expires_at: string
}

export interface CurrentUser {
  user_id: string
  display_name: string
  role: string
}

export interface ClaimScores {
  claim_id: string
  components: ScoreComponent[]
}

// --- Citation statistics (how a work/claim has been cited; scite-parity WP1) ---

export interface CitationStatement {
  assertion_id: string
  citing_work_id: string | null
  citing_claim_id: string | null
  function: string | null
  stance: string | null
  resolution: string
  status: string
  section: string | null
  evidence: EvidenceRef | null
}

export interface CitationTallies {
  total: number
  by_stance: Record<string, number>
  by_function: Record<string, number>
  by_resolution: Record<string, number>
  by_section: Record<string, number>
  abstained: number
}

export interface CitationStats {
  subject_type: string
  subject_id: string
  tallies: CitationTallies
  statements: CitationStatement[]
}

export interface ReportTimelinePoint {
  year: number
  statement_count: number
  citing_work_count: number
}

export interface ReportConflictSummary {
  has_conflicting_stances: boolean
  supporting_statements: number
  contradicting_statements: number
  neutral_or_unclear_statements: number
  conflicting_citing_work_count: number
}

export interface ReportFacets {
  section: Record<string, number>
  function: Record<string, number>
  stance: Record<string, number>
  resolution: Record<string, number>
  year: Record<string, number>
}

export interface ReportAppliedFilters {
  section: string | null
  function: string | null
  stance: string | null
  resolution: string | null
  min_year: number | null
  max_year: number | null
}

export interface PaperReport {
  work_id: string
  total_statements: number
  filtered_statements: number
  facets: ReportFacets
  applied_filters: ReportAppliedFilters
  tallies: CitationTallies
  timeline: ReportTimelinePoint[]
  conflict_summary: ReportConflictSummary
  statements: CitationStatement[]
}

export interface CollectionMemberView {
  collection_membership_id: string
  work_id: string
  title: string | null
  doi: string | null
  pmid: string | null
  year: number | null
  added_at: string
  citation_tallies: CitationTallies | null
  is_retracted: boolean | null
  integrity_notice: string | null
}

export interface CollectionView {
  collection_id: string
  owner_id: string
  name: string
  description: string | null
  member_count: number
  is_watched: boolean
  watch_snapshot_at: string | null
  created_at: string
  updated_at: string
}

export interface CollectionDetailView extends CollectionView {
  aggregate_citation_tallies: CitationTallies | null
  members: CollectionMemberView[]
}

export interface CollectionAddMembersRequest {
  work_ids?: string[]
  dois?: string[]
  pmids?: string[]
  csv_text?: string
}

export interface CollectionAddMembersResult {
  collection_id: string
  added_count: number
  skipped_identifiers: string[]
  created_stub_work_ids: string[]
  members: CollectionMemberView[]
}

export interface CollectionImportResult extends CollectionAddMembersResult {
  format: string
  entry_count: number
  matched_count: number
}

export interface CollectionMemberDelta {
  work_id: string
  title: string | null
  new_support: number
  new_contradict: number
}

export interface CollectionCitationDelta {
  collection_id: string
  has_snapshot: boolean
  snapshot_at: string | null
  new_support_total: number
  new_contradict_total: number
  members: CollectionMemberDelta[]
}

export interface CollectionBulkRemoveResult {
  collection_id: string
  removed_count: number
  removed_work_ids: string[]
}

export interface SearchQuery {
  q: string
  section: string | null
  function: string | null
  stance: string | null
  resolution: string | null
  min_year: number | null
  max_year: number | null
}

export interface SavedSearchView {
  saved_search_id: string
  owner_id: string
  name: string
  query: SearchQuery
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface AlertView {
  alert_id: string
  source_type: string
  source_id: string
  alert_type: string
  work_id: string | null
  claim_id: string | null
  summary: string
  is_read: boolean
  created_at: string
}

export interface AlertRunResult {
  created_count: number
  alerts: AlertView[]
}

export interface ClaimOccurrenceView {
  occurrence_id: string
  passage_id: string
  span_start: number | null
  span_end: number | null
  occurrence_type: string
  extraction_run_id: string
}

export interface TargetCandidate {
  interpretation_id: string
  score: number
}

export interface RelationAssertionView {
  assertion_id: string
  citing_occurrence_id: string
  citation_mention_id: string | null
  evidence_passage_id: string | null
  cited_work_id: string | null
  target_interpretation_id: string | null
  target_candidates: TargetCandidate[]
  function: string | null
  stance: string | null
  scope: string | null
  resolution: string
  target_link_score: number | null
  stance_distribution: Record<string, number> | null
  extraction_run_id: string
  status: string
}

export interface PaperVersionView {
  version_id: string
  manifestation: string
  artifact_hash: string | null
  full_text_available: boolean
  license_status: string | null
  parser_name: string | null
  parser_version: string | null
  parse_status: string | null
}

export interface ExtractionRunView {
  run_id: string
  model: string | null
  provider: string | null
  model_version: string | null
  prompt_template_version: string | null
  parser_version: string | null
  code_revision: string | null
  inference_parameters: Record<string, unknown> | null
  timestamp: string
}

export interface ClaimInterpretationView {
  interpretation_id: string
  claim_occurrence_id: string
  normalized_text: string
  qualifiers: Record<string, unknown> | null
  extraction_run_id: string | null
  author_id: string | null
  parent_interpretation_ids: string[]
  created_by: string | null
  created_at: string
}

export interface RevisionResult {
  new_interpretation: ClaimInterpretationView
  parent_interpretation_id: string
  staled_assertion_ids: string[]
}

export interface ReviewDecisionView {
  review_id: string
  subject_type: string
  subject_id: string
  reviewer_id: string
  decision_dimension: string
  label: string | null
  rationale: string | null
  timestamp: string
}

export interface ClusterMemberView {
  membership_id: string
  interpretation_id: string
  normalized_text: string
  method: string
  membership_confidence: number | null
  status: string
  stance_in_context: string | null
}

export interface ClusterView {
  cluster_id: string
  clustering_method: string | null
  threshold_version: string | null
  members: ClusterMemberView[]
  conflicting_stances: boolean
}

// --- Network graph (papers / authors / citations / claims) ---

export type GraphNodeType = 'paper' | 'author' | 'claim' | string

export interface GraphNode {
  id: string
  type: GraphNodeType
  label: string
  data: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  label: string | null
  data: Record<string, unknown>
}

export interface GraphView {
  nodes: GraphNode[]
  edges: GraphEdge[]
  center_id: string | null
  truncated: boolean
}

// --- Saved maps (persisted seed set + layout; litmaps-parity WP-L2) ---

export interface MapMemberView {
  map_membership_id: string
  work_id: string
  title: string | null
  doi: string | null
  pmid: string | null
  year: number | null
  note: string | null
  position: Record<string, number> | null
  added_at: string
}

export interface MapView {
  map_id: string
  owner_id: string
  name: string
  description: string | null
  layout_config: Record<string, unknown>
  member_count: number
  share_token: string | null
  is_watched: boolean
  watch_last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface MapDetailView extends MapView {
  members: MapMemberView[]
}

export interface MapShareView {
  map_id: string
  share_token: string
}

/** Read-only projection of a shared map, reachable by token without auth. */
export interface SharedMapView {
  map_id: string
  name: string
  description: string | null
  layout_config: Record<string, unknown>
  member_count: number
  members: MapMemberView[]
  created_at: string
  updated_at: string
}

export interface GraphExpansion {
  work_id: string
  references_fetched: number
  works_created: number
  edges_created: number
  skipped_reason: string | null
  graph: GraphView
}

export interface ClaimExpansion {
  interpretation_id: string
  grounded_terms: number
  resolved_terms: number
  corroborating_edges: number
  graph: GraphView
}

// --- Seed-based discovery (ranked connected papers; litmaps-parity WP-L1) ---

export interface DiscoveryCandidate {
  work_id: string | null
  external_id: string | null
  title: string | null
  year: number | null
  connection_score: number
  supporting_seed_ids: string[]
  is_influential: boolean
  in_corpus: boolean
}

export interface DiscoveryResult {
  seed_work_ids: string[]
  candidates: DiscoveryCandidate[]
  seeds_resolved: number
  skipped_seed_ids: string[]
}

// --- Full-text claim search (scite-parity WP2, F3) ---

export interface SearchHit {
  claim_id: string
  normalized_text: string
  occurrence_id: string
  interpretation_id: string
  work_id: string
  paper_title: string | null
  year: number | null
  section: string | null
  function: string[]
  stance: string[]
  resolution: string[]
  evidence: EvidenceRef
}

export interface SearchFacets {
  section: Record<string, number>
  function: Record<string, number>
  stance: Record<string, number>
  resolution: Record<string, number>
}

export interface SearchResults {
  query: string
  total: number
  limit: number
  offset: number
  hits: SearchHit[]
  facets: SearchFacets
}
