import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { MapView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Saved maps list (litmaps-parity WP-L2). Maps are created by saving the current
 * view from the network explorer ("Save as map" on /graph); here you can reopen or
 * delete them. Opening a map hydrates its seed set + layout into the explorer.
 */
export default function MapsPage() {
  const maps = useApi<MapView[]>(() => api.get('/maps'), [])

  async function onDelete(mapId: string) {
    if (!window.confirm('Delete this map? This cannot be undone.')) return
    await api.del(`/maps/${mapId}`)
    maps.reload()
  }

  return (
    <>
      <PageHeading>Saved maps</PageHeading>
      <p className="text-base margin-top-0">
        A saved map is a named seed set of papers plus the layout you were using.
        Create one with <strong>Save as map</strong> in the{' '}
        <Link to="/graph">network explorer</Link>.
      </p>

      {maps.loading && <Loading />}
      {maps.error && <ErrorAlert message={maps.error} />}
      {maps.data && maps.data.length === 0 && <Empty>No saved maps yet.</Empty>}
      {maps.data && maps.data.length > 0 && (
        <table className="usa-table usa-table--borderless width-full">
          <caption className="usa-sr-only">Your saved maps</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Papers</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {maps.data.map((m) => (
              <tr key={m.map_id}>
                <td>
                  <Link to={`/graph?map=${m.map_id}`}>{m.name}</Link>
                  {m.description && (
                    <span className="display-block font-body-3xs text-base">
                      {m.description}
                    </span>
                  )}
                </td>
                <td>{m.member_count}</td>
                <td>
                  <button
                    type="button"
                    className="usa-button usa-button--unstyled text-secondary"
                    onClick={() => onDelete(m.map_id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
