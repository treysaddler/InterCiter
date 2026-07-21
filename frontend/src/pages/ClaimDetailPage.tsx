import { useParams } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

/**
 * Claim detail — the core screen (docs/ui-design.md §6.1, US-1.3–1.8).
 *
 * Consumes: GET /v1/claims/:id, /v1/claims/:id/relationships,
 * /v1/claims/:id/scores, plus audit endpoints behind "show provenance".
 *
 * Provenance-first rules to honor when built:
 *  - verbatim passage pinned beside the normalized claim, char_start/end highlighted
 *  - function and stance as separate tags; paper_resolved labeled as reaching a paper
 *  - abstention (unresolved) is an explicit visual state, not omission
 *  - scores are decomposed chips, never a blended scalar
 */
export default function ClaimDetailPage() {
  const { claimId } = useParams()
  return (
    <>
      <PageHeading>Claim</PageHeading>
      <p>
        Core screen for <code>{claimId}</code>: normalized text beside its verbatim
        source passage, one-hop relations, decomposed scores, explicit abstention.
      </p>
    </>
  )
}
