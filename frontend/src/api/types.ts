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

export interface CurrentUser {
  user_id: string
  display_name: string
  role: string
}
