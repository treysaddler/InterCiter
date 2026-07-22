import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type {
  ClaimOccurrenceView,
  ClaimScores,
  ClaimView,
  ExtractionRunView,
  RelationAssertionView,
} from '../api/types'
import EvidencePane from '../components/EvidencePane'
import PageHeading from '../components/PageHeading'
import RelationList from '../components/RelationList'
import ScoreChips from '../components/ScoreChips'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Claim detail — the core screen (docs/ui-design.md §6.1, US-1.3–1.8).
 *
 * Normalized claim beside its verbatim source passage (span highlighted), one-hop
 * relations (function + stance as separate tags, explicit abstention), decomposed
 * score chips (no blended scalar), and full provenance on demand.
 */
export default function ClaimDetailPage() {
  const { claimId = '' } = useParams()

  const claim = useApi<ClaimView>(() => api.get<ClaimView>(`/claims/${claimId}`), [claimId])
  const occurrenceId = claim.data?.occurrence_id
  const occurrence = useApi<ClaimOccurrenceView | null>(
    () =>
      occurrenceId
        ? api.get<ClaimOccurrenceView>(`/claim-occurrences/${occurrenceId}`)
        : Promise.resolve(null),
    [occurrenceId ?? ''],
  )
  const relationships = useApi<RelationAssertionView[]>(
    () => api.get<RelationAssertionView[]>(`/claims/${claimId}/relationships`),
    [claimId],
  )
  const scores = useApi<ClaimScores>(
    () => api.get<ClaimScores>(`/claims/${claimId}/scores`),
    [claimId],
  )

  if (claim.loading) return <><PageHeading>Claim</PageHeading><Loading /></>
  if (claim.error) return <><PageHeading>Claim</PageHeading><ErrorAlert message={claim.error} /></>
  if (!claim.data) return null

  const c = claim.data

  return (
    <>
      <p className="margin-top-4 margin-bottom-0">
        <Link to={`/papers/${c.work_id}`}>← Paper</Link>
      </p>
      <PageHeading>Claim</PageHeading>

      <div className="grid-row grid-gap">
        {/* Claim + evidence, co-visible (provenance-first). */}
        <div className="tablet:grid-col-8">
          <p className="font-body-lg text-bold margin-bottom-1">{c.normalized_text}</p>
          <p className="font-body-3xs text-base margin-top-0">
            Interpretation · {c.occurrence_type}
          </p>
          <EvidencePane
            evidence={c.evidence}
            spanStart={occurrence.data?.span_start}
            spanEnd={occurrence.data?.span_end}
          />

          <h2 className="margin-top-4">Cited relationships</h2>
          {relationships.loading && <Loading />}
          {relationships.error && <ErrorAlert message={relationships.error} />}
          {relationships.data && <RelationList relations={relationships.data} />}
        </div>

        {/* Decomposed scores + provenance. */}
        <div className="tablet:grid-col-4">
          <h2 className="margin-top-2">Confidence signals</h2>
          {scores.loading && <Loading />}
          {scores.error && <ErrorAlert message={scores.error} />}
          {scores.data && <ScoreChips components={scores.data.components} />}

          <Provenance claim={c} occurrence={occurrence.data} />
        </div>
      </div>
    </>
  )
}

function Provenance({
  claim,
  occurrence,
}: {
  claim: ClaimView
  occurrence: ClaimOccurrenceView | null
}) {
  const [open, setOpen] = useState(false)
  const runId = occurrence?.extraction_run_id
  const run = useApi<ExtractionRunView | null>(
    () => (open && runId ? api.get<ExtractionRunView>(`/extraction-runs/${runId}`) : Promise.resolve(null)),
    [open, runId ?? ''],
  )

  return (
    <div className="margin-top-3">
      <h2>Provenance</h2>
      <button
        type="button"
        className="usa-button usa-button--outline"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? 'Hide provenance' : 'Show provenance'}
      </button>
      {open && (
        <dl className="margin-top-2 font-body-3xs">
          <dt className="text-bold">Occurrence</dt>
          <dd className="margin-left-0">{claim.occurrence_id}</dd>
          <dt className="text-bold">Interpretation</dt>
          <dd className="margin-left-0">{claim.interpretation_id}</dd>
          <dt className="text-bold">Passage</dt>
          <dd className="margin-left-0">{claim.evidence.passage_id}</dd>
          {run.data && (
            <>
              <dt className="text-bold">Extraction run</dt>
              <dd className="margin-left-0">
                {run.data.model ?? 'unknown model'}
                {run.data.prompt_template_version
                  ? ` · ${run.data.prompt_template_version}`
                  : ''}
              </dd>
            </>
          )}
        </dl>
      )}
    </div>
  )
}
