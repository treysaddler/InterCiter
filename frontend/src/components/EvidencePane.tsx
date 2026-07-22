import type { EvidenceRef } from '../api/types'

/**
 * The evidence pane (docs/ui-design.md §4, US-1.3): the claim's verbatim source
 * sentence, with the occurrence's span highlighted **only when it is a valid
 * offset into the text** — never a faked highlight. Occurrence spans are passage-
 * relative (0..len of verbatim_text); a whole-passage span highlights everything,
 * which faithfully means "this entire sentence is the claim".
 */
export default function EvidencePane({
  evidence,
  spanStart,
  spanEnd,
}: {
  evidence: EvidenceRef
  spanStart?: number | null
  spanEnd?: number | null
}) {
  const text = evidence.verbatim_text
  const canHighlight =
    spanStart != null &&
    spanEnd != null &&
    spanStart >= 0 &&
    spanEnd <= text.length &&
    spanStart < spanEnd

  return (
    <aside aria-label="Source passage" className="margin-top-2">
      {evidence.section && (
        <p className="text-bold text-base-dark margin-bottom-1 font-body-3xs text-uppercase">
          {evidence.section}
        </p>
      )}
      <blockquote className="ic-evidence__verbatim margin-0 margin-y-1">
        {canHighlight ? (
          <>
            {text.slice(0, spanStart!)}
            <mark className="ic-evidence__highlight">
              {text.slice(spanStart!, spanEnd!)}
            </mark>
            {text.slice(spanEnd!)}
          </>
        ) : (
          text
        )}
      </blockquote>
      <p className="font-body-3xs text-base margin-0">
        As written · source {evidence.work_id}
      </p>
    </aside>
  )
}
