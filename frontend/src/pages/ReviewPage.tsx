import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { ClaimView, PaperView, RelationAssertionView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

interface QueueItem {
  claimId: string
  workId: string
  text: string
  reasons: string[]
}

/**
 * Reviewer triage queue (US-3.1). Surfaces claims whose cited relationships are
 * unresolved/ambiguous or hold assertions that are stale_pending_review — the
 * items most in need of human attention. Built from existing read endpoints.
 */
async function buildQueue(): Promise<QueueItem[]> {
  const papers = await api.get<PaperView[]>('/papers')
  const claimLists = await Promise.all(
    papers.map((p) =>
      api.get<ClaimView[]>(`/papers/${p.work_id}/claims`).then((cs) => ({ p, cs })),
    ),
  )
  const flat = claimLists.flatMap(({ p, cs }) => cs.map((c) => ({ p, c })))
  const withRels = await Promise.all(
    flat.map(({ p, c }) =>
      api
        .get<RelationAssertionView[]>(`/claims/${c.claim_id}/relationships`)
        .then((rels) => ({ p, c, rels })),
    ),
  )

  const items: QueueItem[] = []
  for (const { p, c, rels } of withRels) {
    const reasons = new Set<string>()
    for (const r of rels) {
      if (r.resolution === 'unresolved' || r.resolution === 'ambiguous') {
        reasons.add(`${r.function ?? 'relation'} · ${r.resolution}`)
      }
      if (r.status === 'stale_pending_review') {
        reasons.add('stale assertion pending review')
      }
    }
    if (reasons.size > 0) {
      items.push({ claimId: c.claim_id, workId: p.work_id, text: c.normalized_text, reasons: [...reasons] })
    }
  }
  return items
}

export default function ReviewPage() {
  const { data, error, loading } = useApi<QueueItem[]>(buildQueue, [])

  return (
    <>
      <PageHeading>Review</PageHeading>
      <p className="usa-intro font-body-sm">
        Claims needing attention: unresolved or ambiguous citations, or assertions
        marked stale after a revision. Open a claim to revise, record a decision, or
        curate its clusters.
      </p>

      {loading && <Loading label="Scanning the corpus…" />}
      {error && <ErrorAlert message={error} />}
      {data && data.length === 0 && <Empty>Nothing in the queue — all clear.</Empty>}
      {data && data.length > 0 && (
        <ul className="usa-list usa-list--unstyled margin-top-2">
          {data.map((item) => (
            <li
              key={item.claimId}
              className="border-1px border-base-lighter radius-md padding-2 margin-bottom-2"
            >
              <Link to={`/papers/${item.workId}/claims/${item.claimId}`}>
                {item.text}
              </Link>
              <div className="margin-top-1">
                {item.reasons.map((r) => (
                  <span key={r} className="usa-tag bg-gold text-ink margin-right-1">
                    {r}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
