import type { ScoreComponent } from '../api/types'

/**
 * Decomposed confidence signals (US-1.7). Each component is its own labeled chip;
 * there is deliberately no blended scalar. A null value renders as "abstained".
 */
export default function ScoreChips({ components }: { components: ScoreComponent[] }) {
  if (!components.length) {
    return <p className="text-base margin-top-1">No score components recorded.</p>
  }
  return (
    <ul className="usa-list usa-list--unstyled margin-top-1">
      {components.map((c) => (
        <li key={c.name} className="ic-score-chip">
          <span className="usa-tag bg-base-lighter text-ink">{c.name}</span>
          <span className="text-bold">
            {c.value == null ? 'abstained' : c.value.toFixed(2)}
          </span>
          {c.algorithm_version && (
            <span className="font-body-3xs text-base">({c.algorithm_version})</span>
          )}
        </li>
      ))}
    </ul>
  )
}
