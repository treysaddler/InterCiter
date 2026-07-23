// Retraction / editorial-notice badges (scite-parity WP5). Null/false flags render
// nothing, so unenriched works stay visually quiet. Reused on collection members,
// paper detail, and reports.
export default function IntegrityBadges({
  isRetracted,
  integrityNotice,
  className,
}: {
  isRetracted?: boolean | null
  integrityNotice?: string | null
  className?: string
}) {
  if (!isRetracted && !integrityNotice) return null
  return (
    <span className={className}>
      {isRetracted && (
        <span className="usa-tag bg-secondary-dark text-white margin-right-05">
          Retracted
        </span>
      )}
      {integrityNotice && (
        <span className="usa-tag bg-accent-warm-dark text-white">
          {integrityNotice.replaceAll('_', ' ')}
        </span>
      )}
    </span>
  )
}
