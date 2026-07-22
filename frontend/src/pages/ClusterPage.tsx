import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { ClusterView } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'

/**
 * Cluster detail (US-3.5–3.6). GET /v1/clusters/:id shows memberships with method +
 * confidence; conflicting stances are surfaced explicitly. Reviewers can soft-remove
 * a bad membership (DELETE sets status removed — nothing is destroyed).
 */
export default function ClusterPage() {
  const { clusterId = '' } = useParams()
  const { user } = useAuth()
  const isReviewer = user != null && (user.role === 'reviewer' || user.role === 'admin')

  const [cluster, setCluster] = useState<ClusterView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    api
      .get<ClusterView>(`/clusters/${clusterId}`)
      .then((c) => active && setCluster(c))
      .catch((e) => active && setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [clusterId])

  async function remove(interpretationId: string) {
    setError(null)
    try {
      const updated = await api.del<ClusterView>(
        `/clusters/${clusterId}/members/${interpretationId}`,
      )
      setCluster(updated)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not remove membership.')
    }
  }

  return (
    <>
      <PageHeading>Cluster</PageHeading>
      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}

      {cluster && (
        <>
          <p className="text-base">
            {cluster.clustering_method ?? 'unknown method'}
            {cluster.threshold_version ? ` · ${cluster.threshold_version}` : ''}
          </p>
          {cluster.conflicting_stances && (
            <div className="usa-alert usa-alert--warning margin-y-2" role="alert">
              <div className="usa-alert__body">
                <h2 className="usa-alert__heading">Conflicting stances</h2>
                <p className="usa-alert__text">
                  Members of this cluster take opposing stances — review before trusting
                  the grouping.
                </p>
              </div>
            </div>
          )}

          <table className="usa-table usa-table--borderless width-full">
            <thead>
              <tr>
                <th scope="col">Claim</th>
                <th scope="col">Confidence</th>
                <th scope="col">Stance</th>
                <th scope="col">Status</th>
                {isReviewer && <th scope="col">Action</th>}
              </tr>
            </thead>
            <tbody>
              {cluster.members.map((m) => (
                <tr key={m.membership_id}>
                  <td>
                    <Link to={`/claims/${m.interpretation_id}`}>{m.normalized_text}</Link>
                  </td>
                  <td>
                    {m.membership_confidence == null
                      ? '—'
                      : m.membership_confidence.toFixed(2)}
                  </td>
                  <td>{m.stance_in_context ?? '—'}</td>
                  <td>
                    <span className="usa-tag bg-base-lighter text-ink">{m.status}</span>
                  </td>
                  {isReviewer && (
                    <td>
                      {m.status === 'active' ? (
                        <button
                          type="button"
                          className="usa-button usa-button--outline usa-button--small"
                          onClick={() => remove(m.interpretation_id)}
                        >
                          Remove
                        </button>
                      ) : (
                        <span className="text-base">removed</span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}
