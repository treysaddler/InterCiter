import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { ClaimView, ClusterView, RevisionResult } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { useApi } from '../hooks/useApi'
import { ErrorAlert } from './States'

/**
 * Reviewer actions on a claim (US-3.2–3.5). Shown only to reviewer/admin. Every
 * action is additive and attributed server-side: revising creates a new
 * interpretation (old as parent) and surfaces any staled assertions; a review
 * decision appends a per-dimension record.
 */
export default function ReviewerPanel({ claim }: { claim: ClaimView }) {
  const { user } = useAuth()
  const isReviewer = user != null && (user.role === 'reviewer' || user.role === 'admin')
  if (!isReviewer) return null

  return (
    <section className="margin-top-4 padding-2 bg-base-lightest radius-md">
      <h2 className="margin-top-0">Reviewer actions</h2>
      <ReviseForm claim={claim} />
      <ReviewDecisionForm interpretationId={claim.interpretation_id} />
      <ClaimClusters claimId={claim.claim_id} />
    </section>
  )
}

function ReviseForm({ claim }: { claim: ClaimView }) {
  const navigate = useNavigate()
  const [text, setText] = useState(claim.normalized_text)
  const [material, setMaterial] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [staled, setStaled] = useState<string[] | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const res = await api.post<RevisionResult>(
        `/claim-interpretations/${claim.interpretation_id}/revisions`,
        { normalized_text: text.trim(), material },
      )
      setStaled(res.staled_assertion_ids)
      // The head moved to a new interpretation id; follow it.
      navigate(`/claims/${res.new_interpretation.interpretation_id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Revision failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="usa-form usa-form--large" onSubmit={onSubmit}>
      <h3>Revise interpretation</h3>
      {error && <ErrorAlert message={error} />}
      {staled && staled.length > 0 && (
        <div className="usa-alert usa-alert--warning usa-alert--slim" role="status">
          <div className="usa-alert__body">
            <p className="usa-alert__text">
              {staled.length} assertion(s) marked stale_pending_review.
            </p>
          </div>
        </div>
      )}
      <label className="usa-label" htmlFor="revise-text">
        Normalized text
      </label>
      <textarea
        className="usa-textarea"
        id="revise-text"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="usa-checkbox">
        <input
          className="usa-checkbox__input"
          id="material"
          type="checkbox"
          checked={material}
          onChange={(e) => setMaterial(e.target.checked)}
        />
        <label className="usa-checkbox__label" htmlFor="material">
          Material revision (marks dependent assertions stale)
        </label>
      </div>
      <button
        className="usa-button margin-top-2"
        type="submit"
        disabled={busy || !text.trim() || text.trim() === claim.normalized_text}
      >
        {busy ? 'Saving…' : 'Save revision'}
      </button>
    </form>
  )
}

const LABELS = ['accepted', 'rejected', 'needs_work']

function ReviewDecisionForm({ interpretationId }: { interpretationId: string }) {
  const [dimension, setDimension] = useState('extraction_fidelity')
  const [label, setLabel] = useState('accepted')
  const [rationale, setRationale] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setDone(false)
    setBusy(true)
    try {
      await api.post('/review-decisions', {
        subject_type: 'claim_interpretation',
        subject_id: interpretationId,
        decision_dimension: dimension.trim(),
        label,
        rationale: rationale.trim() || null,
      })
      setDone(true)
      setRationale('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record decision.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="usa-form usa-form--large margin-top-3" onSubmit={onSubmit}>
      <h3>Record a review decision</h3>
      {error && <ErrorAlert message={error} />}
      {done && (
        <div className="usa-alert usa-alert--success usa-alert--slim" role="status">
          <div className="usa-alert__body">
            <p className="usa-alert__text">Decision recorded.</p>
          </div>
        </div>
      )}
      <label className="usa-label" htmlFor="dimension">
        Dimension
      </label>
      <input
        className="usa-input"
        id="dimension"
        value={dimension}
        onChange={(e) => setDimension(e.target.value)}
      />
      <label className="usa-label" htmlFor="label">
        Label
      </label>
      <select
        className="usa-select"
        id="label"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      >
        {LABELS.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>
      <label className="usa-label" htmlFor="rationale">
        Rationale
      </label>
      <textarea
        className="usa-textarea"
        id="rationale"
        rows={2}
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
      />
      <button className="usa-button margin-top-2" type="submit" disabled={busy || !dimension.trim()}>
        {busy ? 'Recording…' : 'Record decision'}
      </button>
    </form>
  )
}

function ClaimClusters({ claimId }: { claimId: string }) {
  const { data } = useApi<ClusterView[]>(
    () => api.get<ClusterView[]>(`/claims/${claimId}/clusters`),
    [claimId],
  )
  return (
    <div className="margin-top-3">
      <h3>Clusters</h3>
      {!data || data.length === 0 ? (
        <p className="text-base">This claim is not in any cluster.</p>
      ) : (
        <ul className="usa-list">
          {data.map((c) => (
            <li key={c.cluster_id}>
              <Link to={`/clusters/${c.cluster_id}`}>{c.cluster_id}</Link>
              {c.conflicting_stances && (
                <span className="usa-tag bg-gold text-ink margin-left-1">
                  conflicting stances
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
