import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type {
  CollectionAddMembersResult,
  CollectionDetailView,
  CollectionMemberView,
} from '../api/types'
import CitationTallies from '../components/CitationTallies'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const DOI_LIKE = /^10\.\d{4,9}\/\S+$/i

function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') {
    return file.text()
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('read failed'))
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.readAsText(file)
  })
}

function parseIdentifiers(text: string): { dois: string[]; pmids: string[] } {
  const dois: string[] = []
  const pmids: string[] = []
  for (const token of text.split(/[\s,;]+/)) {
    const t = token.trim()
    if (!t) continue
    if (DOI_LIKE.test(t)) dois.push(t)
    else if (/^\d+$/.test(t)) pmids.push(t)
  }
  return {
    dois: Array.from(new Set(dois)),
    pmids: Array.from(new Set(pmids)),
  }
}

/**
 * Collection detail with batch identifier intake.
 */
export default function CollectionDetailPage() {
  const navigate = useNavigate()
  const { collectionId = '' } = useParams()
  const [memberSort, setMemberSort] = useState('added_desc')
  const [memberFilter, setMemberFilter] = useState('')
  const detail = useApi<CollectionDetailView>(
    () =>
      api.get<CollectionDetailView>(
        `/collections/${collectionId}?include_member_tallies=true&member_sort=${memberSort}`,
      ),
    [collectionId, memberSort],
  )
  const [csvText, setCsvText] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savingMeta, setSavingMeta] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const parsed = parseIdentifiers(csvText)
  const normalizedFilter = memberFilter.trim().toLowerCase()
  const filteredMembers = detail.data?.members.filter((member) => {
    if (!normalizedFilter) return true
    return [member.title, member.doi, member.pmid, member.work_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedFilter))
  }) ?? []

  useEffect(() => {
    if (!detail.data) return
    setName(detail.data.name)
    setDescription(detail.data.description ?? '')
  }, [detail.data])

  async function onAddMembers(e: FormEvent) {
    e.preventDefault()
    if (!csvText.trim()) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<CollectionAddMembersResult>(
        `/collections/${collectionId}/members`,
        {
          csv_text: csvText,
          dois: parsed.dois,
          pmids: parsed.pmids,
        },
      )
      const stubCount = result.created_stub_work_ids.length
      const skippedCount = result.skipped_identifiers.length
      setMessage(
        `Added ${result.added_count} member(s)` +
          (stubCount ? `; ${stubCount} created as metadata stubs` : '') +
          (skippedCount ? `; ${skippedCount} skipped` : '') +
          '.',
      )
      setCsvText('')
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function onFileSelected(file: File | null) {
    if (!file) return
    setUploadingFile(true)
    setError(null)
    try {
      const text = await readFileText(file)
      setCsvText((prev) => {
        const trimmed = prev.trim()
        if (!trimmed) return text
        return `${trimmed}\n${text}`
      })
      setMessage(`Loaded identifiers from ${file.name}.`)
    } catch {
      setError('Could not read the selected file.')
    } finally {
      setUploadingFile(false)
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

  async function onSaveMetadata(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSavingMeta(true)
    setError(null)
    setMessage(null)
    try {
      await api.patch(`/collections/${collectionId}`, {
        name: name.trim(),
        description: description.trim() || null,
      })
      setMessage('Collection details updated.')
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSavingMeta(false)
    }
  }

  async function onDeleteCollection() {
    if (!window.confirm('Delete this collection and all memberships?')) return
    setDeleting(true)
    setError(null)
    setMessage(null)
    try {
      await api.del(`/collections/${collectionId}`)
      navigate('/collections')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setDeleting(false)
    }
  }

  function onExportMembers() {
    if (!detail.data || detail.data.members.length === 0) return
    const lines = ['work_id,doi,pmid,title']
    for (const member of detail.data.members) {
      const safeTitle = (member.title ?? '').replaceAll('"', '""')
      lines.push(
        [
          member.work_id,
          member.doi ?? '',
          member.pmid ?? '',
          `"${safeTitle}"`,
        ].join(','),
      )
    }
    const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${collectionId}-members.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  function onExportIdentifiersTxt() {
    if (filteredMembers.length === 0) return
    const ids = Array.from(
      new Set(
        filteredMembers.flatMap((member) => [member.doi, member.pmid]).filter(Boolean),
      ),
    )
    if (ids.length === 0) return
    const blob = new Blob([ids.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${collectionId}-identifiers.txt`
    anchor.click()
    URL.revokeObjectURL(url)
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
          <h2>Manage collection</h2>
          <form className="usa-form maxw-tablet" onSubmit={onSaveMetadata}>
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
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="display-flex flex-align-center flex-wrap">
              <button type="submit" className="usa-button margin-right-1" disabled={savingMeta}>
                {savingMeta ? 'Saving…' : 'Save details'}
              </button>
              <button
                type="button"
                className="usa-button usa-button--outline"
                onClick={onDeleteCollection}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete collection'}
              </button>
            </div>
          </form>

          <h2>Batch add members</h2>
          <p className="font-body-3xs text-base margin-top-0">
            Paste DOIs and PMIDs (comma, semicolon, whitespace, or newline separated).
          </p>
          <label className="usa-label" htmlFor="identifiers-file">Upload CSV/TXT</label>
          <input
            id="identifiers-file"
            className="usa-file-input"
            type="file"
            accept=".csv,.txt,text/csv,text/plain"
            onChange={(e) => {
              const file = e.currentTarget.files?.[0] ?? null
              void onFileSelected(file)
            }}
          />
          {uploadingFile && (
            <p className="font-body-3xs text-base margin-top-05 margin-bottom-0">
              Reading file…
            </p>
          )}
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
            {(parsed.dois.length > 0 || parsed.pmids.length > 0) && (
              <div className="margin-top-1" aria-live="polite">
                <p className="font-body-3xs text-base margin-y-05">
                  Ready to import: {parsed.dois.length} DOI(s), {parsed.pmids.length} PMID(s)
                </p>
                <div className="display-flex flex-wrap">
                  {parsed.dois.slice(0, 8).map((doi) => (
                    <span key={doi} className="usa-tag bg-base-lighter text-ink margin-right-05 margin-bottom-05">
                      DOI {doi}
                    </span>
                  ))}
                  {parsed.pmids.slice(0, 8).map((pmid) => (
                    <span key={pmid} className="usa-tag bg-base-lighter text-ink margin-right-05 margin-bottom-05">
                      PMID {pmid}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <button type="submit" className="usa-button" disabled={saving}>
              {saving ? 'Adding…' : 'Add members'}
            </button>
          </form>

          {message && <p className="text-green">{message}</p>}
          {error && <ErrorAlert message={error} />}

          <h2 className="margin-top-4">Collection citation summary</h2>
          {detail.data.aggregate_citation_tallies ? (
            <CitationTallies tallies={detail.data.aggregate_citation_tallies} />
          ) : (
            <Empty>No aggregate citation data available yet.</Empty>
          )}

          <h2 className="margin-top-4">Members</h2>
          {detail.data.members.length === 0 && <Empty>No members yet.</Empty>}
          {detail.data.members.length > 0 && (
            <>
              <div className="maxw-card margin-bottom-2">
                <label className="usa-label" htmlFor="member-filter">Filter members</label>
                <input
                  id="member-filter"
                  className="usa-input"
                  value={memberFilter}
                  onChange={(e) => setMemberFilter(e.target.value)}
                  placeholder="Search title, DOI, PMID, or work ID"
                />
                <button
                  type="button"
                  className="usa-button usa-button--outline margin-top-1"
                  onClick={onExportMembers}
                >
                  Export members CSV
                </button>
                <button
                  type="button"
                  className="usa-button usa-button--outline margin-top-1 margin-left-1"
                  onClick={onExportIdentifiersTxt}
                >
                  Export identifiers TXT
                </button>
              </div>
              <div className="maxw-card margin-bottom-2">
                <label className="usa-label" htmlFor="member-sort">Sort members</label>
                <select
                  id="member-sort"
                  className="usa-select"
                  value={memberSort}
                  onChange={(e) => setMemberSort(e.target.value)}
                >
                  <option value="added_desc">Recently added</option>
                  <option value="added_asc">Oldest added</option>
                  <option value="support_desc">Most supporting citations</option>
                  <option value="contradict_desc">Most contradicting citations</option>
                </select>
              </div>
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
                {filteredMembers.map((member) => (
                  <tr key={member.collection_membership_id}>
                    <td>
                      <Link to={`/papers/${member.work_id}`}>
                        {member.title ?? member.work_id}
                      </Link>
                      {member.citation_tallies && (
                        <details className="margin-top-1">
                          <summary className="font-body-3xs">
                            Citation tallies
                          </summary>
                          <CitationTallies tallies={member.citation_tallies} />
                        </details>
                      )}
                    </td>
                    <td>{member.year ?? '—'}</td>
                    <td>
                      {[member.doi && `DOI ${member.doi}`, member.pmid && `PMID ${member.pmid}`]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </td>
                    <td>
                      <Link to={`/papers/${member.work_id}/report`}>Report</Link>
                      {' · '}
                      <Link to={`/graph/papers/${member.work_id}`}>Graph</Link>
                      {' · '}
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
              {filteredMembers.length === 0 && (
                <p className="text-base margin-top-1 margin-bottom-0">
                  No members match this filter.
                </p>
              )}
            </>
          )}
        </>
      )}
    </>
  )
}
