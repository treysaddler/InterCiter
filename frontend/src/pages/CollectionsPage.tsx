import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { CollectionView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Collections list/create (scite-parity WP4, F5).
 */
export default function CollectionsPage() {
  const navigate = useNavigate()
  const collections = useApi<CollectionView[]>(() => api.get('/collections'), [])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setError(null)
    setSaving(true)
    try {
      const created = await api.post<CollectionView>('/collections', {
        name: name.trim(),
        description: description.trim() || undefined,
      })
      setName('')
      setDescription('')
      collections.reload()
      navigate(`/collections/${created.collection_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeading>Collections</PageHeading>
      <p className="text-base margin-top-0">
        Curate sets of papers and monitor how their citation evidence evolves.
      </p>

      <h2>Create collection</h2>
      <form className="usa-form maxw-tablet" onSubmit={onCreate}>
        <label className="usa-label" htmlFor="collection-name">Name</label>
        <input
          id="collection-name"
          className="usa-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <label className="usa-label" htmlFor="collection-description">Description</label>
        <textarea
          id="collection-description"
          className="usa-textarea"
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <button type="submit" className="usa-button" disabled={saving}>
          {saving ? 'Creating…' : 'Create collection'}
        </button>
      </form>

      {error && <ErrorAlert message={error} />}

      <h2 className="margin-top-4">Your collections</h2>
      {collections.loading && <Loading />}
      {collections.error && <ErrorAlert message={collections.error} />}
      {collections.data && collections.data.length === 0 && (
        <Empty>No collections yet.</Empty>
      )}
      {collections.data && collections.data.length > 0 && (
        <ul className="usa-list">
          {collections.data.map((collection) => (
            <li key={collection.collection_id}>
              <Link to={`/collections/${collection.collection_id}`}>{collection.name}</Link>
              <span className="font-body-3xs text-base"> · {collection.member_count} members</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
