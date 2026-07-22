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
