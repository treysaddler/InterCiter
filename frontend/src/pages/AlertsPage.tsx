import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { AlertRunResult, AlertView, SavedSearchView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const ALERT_TYPE_LABELS: Record<string, string> = {
  new_claim: 'New matching claim',
  new_support: 'New supporting citation',
  new_contradict: 'New contradicting citation',
  retraction: 'Retraction',
}

function alertTag(alertType: string): string {
  if (alertType === 'retraction' || alertType === 'new_contradict') {
    return 'usa-tag bg-secondary-dark text-white'
  }
  if (alertType === 'new_support') return 'usa-tag bg-success-dark text-white'
  return 'usa-tag'
}

/**
 * Monitoring surface (scite-parity WP8). Lists saved searches (run / delete) and the
 * in-app alert feed (mark read), plus a "Check now" action that re-runs every saved
 * search and watched collection via POST /v1/alerts/run.
 */
export default function AlertsPage() {
  const searches = useApi<SavedSearchView[]>(
    () => api.get<SavedSearchView[]>('/saved-searches'),
    [],
  )
  const alerts = useApi<AlertView[]>(() => api.get<AlertView[]>('/alerts'), [])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function reloadAll() {
    searches.reload()
    alerts.reload()
  }

  async function onCheckNow() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<AlertRunResult>('/alerts/run')
      setMessage(
        result.created_count > 0
          ? `${result.created_count} new alert(s).`
          : 'No new signals since the last check.',
      )
      reloadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function onRunSearch(id: string) {
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<AlertRunResult>(`/saved-searches/${id}/run`)
      setMessage(
        result.created_count > 0
          ? `${result.created_count} new match(es).`
          : 'No new matches.',
      )
      reloadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function onDeleteSearch(id: string) {
    if (!window.confirm('Delete this saved search?')) return
    setError(null)
    try {
      await api.del(`/saved-searches/${id}`)
      searches.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function onMarkRead(id: string) {
    setError(null)
    try {
      await api.post(`/alerts/${id}/read`)
      alerts.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function onMarkAllRead() {
    setError(null)
    try {
      await api.post('/alerts/read-all')
      alerts.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  function searchHref(search: SavedSearchView): string {
    const params = new URLSearchParams()
    if (search.query.q) params.set('q', search.query.q)
    for (const key of ['section', 'function', 'stance', 'resolution'] as const) {
      const value = search.query[key]
      if (value) params.set(key, value)
    }
    return `/search?${params.toString()}`
  }

  return (
    <>
      <PageHeading>Alerts &amp; saved searches</PageHeading>
      <p className="text-base">
        Monitor new supporting or contradicting citations and retractions on your
        watched collections, and new claims matching your saved searches.
      </p>

      <div className="display-flex flex-wrap flex-align-center">
        <button
          type="button"
          className="usa-button margin-right-1"
          onClick={onCheckNow}
          disabled={busy}
        >
          {busy ? 'Checking…' : 'Check now'}
        </button>
      </div>
      {message && <p className="text-green">{message}</p>}
      {error && <ErrorAlert message={error} />}

      <h2 className="margin-top-4">Saved searches</h2>
      {searches.loading && <Loading />}
      {searches.error && <ErrorAlert message={searches.error} />}
      {searches.data && searches.data.length === 0 && (
        <Empty>
          No saved searches yet. Run a search and choose “Save this search”.
        </Empty>
      )}
      {searches.data && searches.data.length > 0 && (
        <ul className="usa-list usa-list--unstyled">
          {searches.data.map((search) => (
            <li
              key={search.saved_search_id}
              className="padding-y-1 border-bottom border-base-lighter"
            >
              <Link to={searchHref(search)}>{search.name}</Link>
              {search.query.q && (
                <span className="font-body-3xs text-base"> · “{search.query.q}”</span>
              )}
              <div className="margin-top-05">
                <button
                  type="button"
                  className="usa-button usa-button--outline usa-button--unstyled margin-right-2"
                  onClick={() => onRunSearch(search.saved_search_id)}
                >
                  Check
                </button>
                <button
                  type="button"
                  className="usa-button usa-button--unstyled text-secondary"
                  onClick={() => onDeleteSearch(search.saved_search_id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="display-flex flex-align-center flex-justify margin-top-4">
        <h2 className="margin-bottom-0">Alert feed</h2>
        {alerts.data && alerts.data.some((a) => !a.is_read) && (
          <button
            type="button"
            className="usa-button usa-button--outline"
            onClick={onMarkAllRead}
          >
            Mark all read
          </button>
        )}
      </div>
      {alerts.loading && <Loading />}
      {alerts.error && <ErrorAlert message={alerts.error} />}
      {alerts.data && alerts.data.length === 0 && (
        <Empty>No alerts yet. Watch a collection or save a search, then “Check now”.</Empty>
      )}
      {alerts.data && alerts.data.length > 0 && (
        <ul className="usa-list usa-list--unstyled">
          {alerts.data.map((alert) => (
            <li
              key={alert.alert_id}
              className={`padding-y-1 border-bottom border-base-lighter${
                alert.is_read ? ' text-base' : ''
              }`}
            >
              <span className={`${alertTag(alert.alert_type)} margin-right-1`}>
                {ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
              </span>
              {alert.work_id ? (
                <Link to={`/papers/${alert.work_id}`}>{alert.summary}</Link>
              ) : (
                <span>{alert.summary}</span>
              )}
              {!alert.is_read && (
                <button
                  type="button"
                  className="usa-button usa-button--unstyled margin-left-1"
                  onClick={() => onMarkRead(alert.alert_id)}
                >
                  Mark read
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
