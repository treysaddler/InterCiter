import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { PaperView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/** Paper list (US-1.1–1.2). Consumes GET /v1/papers. */
export default function PapersPage() {
  const { data, error, loading } = useApi<PaperView[]>(
    () => api.get<PaperView[]>('/papers'),
    [],
  )

  return (
    <>
      <PageHeading>Papers</PageHeading>
      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}
      {data && data.length === 0 && (
        <Empty>
          No papers ingested yet. <Link to="/ingest">Submit one</Link>.
        </Empty>
      )}
      {data && data.length > 0 && (
        <table className="usa-table usa-table--borderless width-full margin-top-2">
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">Year</th>
              <th scope="col">Availability</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.work_id}>
                <td>
                  <Link to={`/papers/${p.work_id}`}>{p.title ?? p.work_id}</Link>
                </td>
                <td>{p.year ?? '—'}</td>
                <td>
                  <span className="usa-tag bg-base-lighter text-ink">
                    {p.availability_state}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
