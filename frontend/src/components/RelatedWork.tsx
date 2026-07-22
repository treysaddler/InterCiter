import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { DiscoveryResult } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ErrorAlert, Loading } from './States'

/**
 * "Dive deeper" — seed-based discovery (litmaps-parity WP-L1, US: find related work).
 *
 * Ranks papers connected to this one by how many of its references they share, via
 * POST /v1/discovery/seeds. Discovery reads from Semantic Scholar (a network call), so
 * it is auth-gated exactly like graph expansion. Nothing is persisted — candidates are
 * suggestions; in-corpus hits deep-link, the rest show a Semantic Scholar id.
 */
export default function RelatedWork({ workId }: { workId: string }) {
  const { status } = useAuth()
  const [result, setResult] = useState<DiscoveryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function findRelated() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post<DiscoveryResult>('/discovery/seeds', {
        seed_work_ids: [workId],
        limit: 20,
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Discovery failed.')
    } finally {
      setLoading(false)
    }
  }

  if (status !== 'authenticated') {
    return (
      <p className="font-body-3xs text-base margin-top-1">
        <Link to="/login">Sign in</Link> to find related work from Semantic Scholar.
      </p>
    )
  }

  return (
    <div className="margin-top-1">
      <button
        type="button"
        className="usa-button usa-button--outline"
        onClick={findRelated}
        disabled={loading}
      >
        {loading ? 'Finding…' : result ? 'Refresh related work' : 'Find related work'}
      </button>

      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}

      {result && !loading && (
        <>
          {result.seeds_resolved === 0 ? (
            <p className="text-base margin-top-2">
              This paper has no DOI, PMID, or Semantic Scholar id to search with.
            </p>
          ) : result.candidates.length === 0 ? (
            <p className="text-base margin-top-2">No connected papers found.</p>
          ) : (
            <ol className="usa-list margin-top-2">
              {result.candidates.map((c) => (
                <li
                  key={c.work_id ?? c.external_id ?? c.title ?? ''}
                  className="margin-bottom-1"
                >
                  {c.in_corpus && c.work_id ? (
                    <Link to={`/papers/${c.work_id}`}>{c.title ?? c.work_id}</Link>
                  ) : (
                    <span>{c.title ?? c.external_id ?? 'Untitled'}</span>
                  )}
                  {c.year != null && (
                    <span className="font-body-3xs text-base"> · {c.year}</span>
                  )}
                  <span className="usa-tag bg-base-lighter text-ink margin-left-1">
                    {c.connection_score} shared
                  </span>
                  {c.is_influential && (
                    <span className="usa-tag bg-mint text-ink margin-left-05">
                      influential
                    </span>
                  )}
                  {!c.in_corpus && c.external_id && (
                    <span className="font-body-3xs text-base margin-left-1">
                      not in corpus · {c.external_id}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}
