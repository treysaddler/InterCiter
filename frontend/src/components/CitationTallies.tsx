import type { CitationTallies } from '../api/types'

/**
 * Aggregate "how has this been cited" tallies (scite-parity WP1, US derived from
 * scite Smart Citations / Reports). Unlike scite's single supporting/contrasting/
 * mentioning label, InterCiter keeps stance and function as SEPARATE dimensions and
 * surfaces abstention explicitly rather than folding it into "mentioning".
 */

const STANCE_COLOR: Record<string, string> = {
  support: 'bg-mint text-ink',
  contradict: 'bg-red text-white',
  neutral: 'bg-base-lighter text-ink',
  unclear: 'bg-gold text-ink',
}

function CountRow({
  label,
  counts,
  colors,
}: {
  label: string
  counts: Record<string, number>
  colors?: Record<string, string>
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  if (!entries.length) return null
  return (
    <div className="margin-bottom-1">
      <span className="font-body-3xs text-base text-uppercase">{label}</span>
      <ul className="usa-list usa-list--unstyled display-flex flex-wrap margin-top-05">
        {entries.map(([key, count]) => (
          <li key={key} className="margin-right-1 margin-bottom-05">
            <span className={`usa-tag ${colors?.[key] ?? 'bg-base-lighter text-ink'}`}>
              {key}
            </span>
            <span className="text-bold margin-left-05">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function CitationTallies({ tallies }: { tallies: CitationTallies }) {
  if (tallies.total === 0) {
    return (
      <p className="text-base margin-top-1">
        No citing statements recorded in the corpus yet.
      </p>
    )
  }
  return (
    <div className="margin-top-1">
      <p className="margin-top-0 margin-bottom-1">
        <span className="text-bold">{tallies.total}</span> citing statement
        {tallies.total === 1 ? '' : 's'}
        {tallies.abstained > 0 && (
          <span className="font-body-3xs text-base">
            {' '}· {tallies.abstained} abstained (no function or stance)
          </span>
        )}
      </p>
      <CountRow label="Stance" counts={tallies.by_stance} colors={STANCE_COLOR} />
      <CountRow label="Function" counts={tallies.by_function} />
      <CountRow label="Resolution" counts={tallies.by_resolution} />
      <CountRow label="Section" counts={tallies.by_section} />
    </div>
  )
}
