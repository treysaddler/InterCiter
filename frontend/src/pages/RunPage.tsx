import { useParams } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

/**
 * Extraction-run provenance. Consumes: GET /v1/extraction-runs/:runId
 * (model, prompt version, parameters, code revision).
 */
export default function RunPage() {
  const { runId } = useParams()
  return (
    <>
      <PageHeading>Extraction run</PageHeading>
      <p>
        Full run provenance for <code>{runId}</code>. Endpoint:{' '}
        <code>GET /v1/extraction-runs/:runId</code>.
      </p>
    </>
  )
}
