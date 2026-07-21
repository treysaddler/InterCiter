import PageHeading from '../components/PageHeading'

/**
 * Reviewer workspace (US-3.1–3.7). Role-gated (reviewer/admin).
 *
 * Consumes: revision, review-decision, and cluster endpoints. Writes are additive
 * and attributed to the authenticated principal (docs/ui-design.md §6.4).
 */
export default function ReviewPage() {
  return (
    <>
      <PageHeading>Review</PageHeading>
      <p>
        Triage queue for low-confidence, unresolved, and <code>stale_pending_review</code>{' '}
        items — revise interpretations, record decisions, and curate clusters.
        Role-gated to reviewer / admin.
      </p>
    </>
  )
}
