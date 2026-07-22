import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

import type { RelationAssertionView } from '../api/types'

/**
 * One-hop cited relationships (US-1.4–1.6). Function and stance are shown as
 * SEPARATE tags (never merged); resolution state is explicit. Abstention
 * (`unresolved` / no target) is a labeled state, not an omission. A
 * `paper_resolved` hop is labeled as reaching the paper, not a specific claim.
 */

const STANCE_COLOR: Record<string, string> = {
  support: 'bg-mint text-ink',
  contradict: 'bg-red text-white',
  neutral: 'bg-base-lighter text-ink',
}

function Tag({ children, className = 'bg-base-lighter text-ink' }: {
  children: ReactNode
  className?: string
}) {
  return <span className={`usa-tag ${className}`}>{children}</span>
}

function RelationCard({ r }: { r: RelationAssertionView }) {
  const abstained = r.resolution === 'unresolved' || r.resolution === 'ambiguous'
  return (
    <li className="border-1px border-base-lighter radius-md padding-2 margin-bottom-2">
      <div className="display-flex flex-wrap flex-align-center margin-bottom-1">
        {r.function ? <Tag>function: {r.function}</Tag> : <Tag>function: —</Tag>}
        <span className="margin-left-1">
          {r.stance ? (
            <Tag className={STANCE_COLOR[r.stance] ?? 'bg-base-lighter text-ink'}>
              stance: {r.stance}
            </Tag>
          ) : (
            <Tag>stance: —</Tag>
          )}
        </span>
        <span className="margin-left-1">
          <Tag className={abstained ? 'bg-gold text-ink' : 'bg-base-lighter text-ink'}>
            {r.resolution}
          </Tag>
        </span>
        {r.status !== 'active' && (
          <span className="margin-left-1">
            <Tag className="bg-gold text-ink">{r.status}</Tag>
          </span>
        )}
      </div>

      {r.target_link_score != null && (
        <p className="font-body-3xs text-base margin-0">
          target link score: {r.target_link_score.toFixed(2)}
        </p>
      )}

      <div className="margin-top-1">
        {r.target_interpretation_id ? (
          <Link to={`/claims/${r.target_interpretation_id}`}>Go to matched claim →</Link>
        ) : r.cited_work_id ? (
          <span>
            <Link to={`/papers/${r.cited_work_id}`}>Go to cited paper →</Link>{' '}
            <span className="font-body-3xs text-base">
              (resolved to the paper, not a specific claim)
            </span>
          </span>
        ) : (
          <span className="text-base">
            Abstained — no confident target ({r.resolution}).
          </span>
        )}
      </div>
    </li>
  )
}

export default function RelationList({
  relations,
}: {
  relations: RelationAssertionView[]
}) {
  if (!relations.length) {
    return <p className="text-base margin-top-1">No cited relationships for this claim.</p>
  }
  return (
    <ul className="usa-list usa-list--unstyled margin-top-1">
      {relations.map((r) => (
        <RelationCard key={r.assertion_id} r={r} />
      ))}
    </ul>
  )
}
