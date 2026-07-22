import { FormEvent, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type {
  CollectionAddMembersResult,
  CollectionDetailView,
  CollectionMemberView,
} from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Collection detail with batch identifier intake.
 */
export default function CollectionDetailPage() {
  const { collectionId = '' } = useParams()
  const detail = useApi<CollectionDetailView>(
    () => api.get<CollectionDetailView>(`/collections/${collectionId}`),
    [collectionId],
  )
  const [csvText, setCsvText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onAddMembers(e: FormEvent) {
    e.preventDefault()
    if (!csvText.trim()) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<CollectionAddMembersResult>(
        `/collections/${collectionId}/members`,
        { csv_text: csvText },
      )
      setMessage(`Added ${result.added_count} member(s).`)
      setCsvText('')
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function onRemove(member: CollectionMemberView) {
    setError(null)
    try {
      await api.del(`/collections/${collectionId}/members/${member.work_id}`)
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <>
      <p className="margin-top-4 margin-bottom-0">
        <Link to="/collections">← Collections</Link>
      </p>
      <PageHeading>{detail.data?.name ?? 'Collection'}</PageHeading>

      {detail.loading && <Loading />}
      {detail.error && <ErrorAlert message={detail.error} />}

      {detail.data && (
        <>
          {detail.data.description && (
            <p className="text-base margin-top-0">{detail.data.description}</p>
          )}

          <h2>Batch add members</h2>
          <p className="font-body-3xs text-base margin-top-0">
            Paste DOIs and PMIDs (comma, semicolon, whitespace, or newline separated).
          </p>
          <form className="usa-form maxw-tablet" onSubmit={onAddMembers}>
            <label className="usa-label" htmlFor="identifiers">Identifiers</label>
            <textarea
              id="identifiers"
              className="usa-textarea"
              rows={5}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder="10.1000/example-doi\n12345678"
            />
            <button type="submit" className="usa-button" disabled={saving}>
              {saving ? 'Adding…' : 'Add members'}
            </button>
          </form>

          {message && <p className="text-green">{message}</p>}
          {error && <ErrorAlert message={error} />}

          <h2 className="margin-top-4">Members</h2>
          {detail.data.members.length === 0 && <Empty>No members yet.</Empty>}
          {detail.data.members.length > 0 && (
            <table className="usa-table width-full">
              <caption className="usa-sr-only">Collection members</caption>
              <thead>
                <tr>
                  <th scope="col">Paper</th>
                  <th scope="col">Year</th>
                  <th scope="col">Identifiers</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {detail.data.members.map((member) => (
                  <tr key={member.collection_membership_id}>
                    <td>
                      <Link to={`/papers/${member.work_id}`}>
                        {member.title ?? member.work_id}
                      </Link>
                    </td>
                    <td>{member.year ?? '—'}</td>
                    <td>
                      {[member.doi && `DOI ${member.doi}`, member.pmid && `PMID ${member.pmid}`]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="usa-button usa-button--unstyled"
                        onClick={() => onRemove(member)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  )
}
