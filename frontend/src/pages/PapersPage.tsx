import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { PaperLookupResult, PaperView } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Quick-add: fetch a paper (+ its citation edges) from Semantic Scholar by id and
 * cache it locally. A read-through cache — browsing this way bootstraps the corpus
 * without the full bulk-dataset download. Consumes POST /v1/papers/lookup.
 */
function QuickAdd({ onAdded }: { onAdded: () => void }) {
  const [id, setId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const value = id.trim()
    if (!value) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await api.post<PaperLookupResult>('/papers/lookup', { external_id: value })
      const title = res.paper.title ?? res.paper.work_id
      setNotice(
        res.cache_hit
          ? `Already cached: ${title}.`
          : `Added ${title} (+${res.edges_created} citation edge(s), ${res.stubs_created} stub(s)).`,
      )
      setId('')
      onAdded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Lookup failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="usa-form usa-form--large margin-top-2" onSubmit={onSubmit}>
      <label className="usa-label margin-top-0" htmlFor="s2-id">
        Fetch from Semantic Scholar
      </label>
      <span className="usa-hint" id="s2-id-hint">
        DOI, PMID:…, CorpusId:…, or a paperId hash.
      </span>
      <div className="display-flex flex-align-end">
        <input
          className="usa-input margin-top-1"
          id="s2-id"
          aria-describedby="s2-id-hint"
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="10.1038/nature14539"
        />
        <button
          className="usa-button margin-left-1 margin-top-0"
          type="submit"
          disabled={busy || !id.trim()}
        >
          {busy ? 'Fetching…' : 'Fetch'}
        </button>
      </div>
      {error && <ErrorAlert message={error} />}
      {notice && (
        <p className="usa-alert usa-alert--success usa-alert--slim margin-top-1" role="status">
          <span className="usa-alert__body">{notice}</span>
        </p>
      )}
    </form>
  )
}

/** Paper list (US-1.1–1.2). Consumes GET /v1/papers. */
export default function PapersPage() {
  const { status } = useAuth()
  const { data, error, loading, reload } = useApi<PaperView[]>(
    () => api.get<PaperView[]>('/papers'),
    [],
  )

  return (
    <>
      <PageHeading>Papers</PageHeading>
      {status === 'authenticated' && <QuickAdd onAdded={reload} />}
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
