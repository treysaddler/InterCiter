import PageHeading from '../components/PageHeading'

/**
 * Paper list (US-1.1–1.2). Consumes: GET /v1/papers.
 * Renders availability_state as a tag; rows link to paper detail.
 */
export default function PapersPage() {
  return (
    <>
      <PageHeading>Papers</PageHeading>
      <p>
        Will list papers with their <code>availability_state</code>, filterable, each
        row linking to detail. Endpoint: <code>GET /v1/papers</code>.
      </p>
    </>
  )
}
