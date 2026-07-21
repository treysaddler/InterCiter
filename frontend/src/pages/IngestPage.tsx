import PageHeading from '../components/PageHeading'

/**
 * Submit a paper (US-2.1–2.2). Consumes: POST /v1/papers with an idempotency key;
 * redirects to the job page to poll.
 */
export default function IngestPage() {
  return (
    <>
      <PageHeading>Submit a paper</PageHeading>
      <p>
        DOI / PMID / open-access XML form with an idempotency key. Endpoint:{' '}
        <code>POST /v1/papers</code> → returns a job.
      </p>
    </>
  )
}
