import { useParams } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

/**
 * Paper detail (US-1.1). Consumes: GET /v1/papers/:id,
 * GET /v1/papers/:id/versions, GET /v1/papers/:id/claims.
 */
export default function PaperDetailPage() {
  const { workId } = useParams()
  return (
    <>
      <PageHeading>Paper</PageHeading>
      <p>
        Metadata, availability state, versions, and claim list for{' '}
        <code>{workId}</code>.
      </p>
    </>
  )
}
