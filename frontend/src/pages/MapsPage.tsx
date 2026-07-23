import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { MapShareView, MapView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

function shareUrl(token: string): string {
  return `${window.location.origin}/shared/${token}`
}

/**
 * Saved maps list (litmaps-parity WP-L2). Maps are created by saving the current
 * view from the network explorer ("Save as map" on /graph); here you can reopen,
 * share (read-only link, WP-L4), or delete them. Opening a map hydrates its seed set
 * + layout into the explorer.
 */
export default function MapsPage() {
  const maps = useApi<MapView[]>(() => api.get('/maps'), [])
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  async function copyLink(token: string) {
    const url = shareUrl(token)
    try {
      await navigator.clipboard?.writeText(url)
      setNotice(`Copied read-only link to clipboard: ${url}`)
    } catch {
      // Clipboard may be unavailable (e.g. insecure context); surface the URL anyway.
      setNotice(`Read-only link: ${url}`)
    }
  }

  async function onShare(mapId: string) {
    setActionError(null)
    try {
      const res = await api.post<MapShareView>(`/maps/${mapId}/share`)
      await copyLink(res.share_token)
      maps.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  async function onRevoke(mapId: string) {
    if (!window.confirm('Revoke the share link? The existing link will stop working.'))
      return
    setActionError(null)
    setNotice(null)
    try {
      await api.del(`/maps/${mapId}/share`)
      maps.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

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

      {notice && (
        <div className="usa-alert usa-alert--success usa-alert--slim margin-y-2" role="status">
          <div className="usa-alert__body">
            <p className="usa-alert__text">{notice}</p>
          </div>
        </div>
      )}
      {actionError && <ErrorAlert message={actionError} />}

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
              <th scope="col">Sharing</th>
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
                  {m.share_token ? (
                    <>
                      <button
                        type="button"
                        className="usa-button usa-button--unstyled"
                        onClick={() => copyLink(m.share_token as string)}
                      >
                        Copy link
                      </button>
                      <button
                        type="button"
                        className="usa-button usa-button--unstyled text-secondary margin-left-2"
                        onClick={() => onRevoke(m.map_id)}
                      >
                        Revoke
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="usa-button usa-button--unstyled"
                      onClick={() => onShare(m.map_id)}
                    >
                      Share
                    </button>
                  )}
                </td>
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
