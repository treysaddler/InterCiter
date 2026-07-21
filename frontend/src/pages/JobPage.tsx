import { useParams } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

/**
 * Job status (US-2.3). Polls GET /v1/jobs/:jobId; on success links to run + paper.
 */
export default function JobPage() {
  const { jobId } = useParams()
  return (
    <>
      <PageHeading>Job</PageHeading>
      <p>
        Polls status for <code>{jobId}</code> and links to the run and paper on
        success. Endpoint: <code>GET /v1/jobs/:jobId</code>.
      </p>
    </>
  )
}
