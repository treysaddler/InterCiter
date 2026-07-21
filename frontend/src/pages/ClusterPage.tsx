import { useParams } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

/**
 * Cluster detail (US-3.5–3.6). Consumes: GET /v1/clusters/:id;
 * DELETE /v1/clusters/:id/members/:interpretationId (sets status removed).
 * Conflicting stances are surfaced explicitly.
 */
export default function ClusterPage() {
  const { clusterId } = useParams()
  return (
    <>
      <PageHeading>Cluster</PageHeading>
      <p>
        Memberships (method + confidence) for <code>{clusterId}</code>, with
        conflicting stances surfaced explicitly.
      </p>
    </>
  )
}
