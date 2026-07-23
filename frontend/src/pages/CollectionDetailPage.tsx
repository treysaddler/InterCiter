import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type {
  CollectionAddMembersResult,
  CollectionCitationDelta,
  CollectionDetailView,
  CollectionImportResult,
  CollectionMemberView,
} from '../api/types'
import CitationTallies from '../components/CitationTallies'
import IntegrityBadges from '../components/IntegrityBadges'
import PageHeading from '../components/PageHeading'
import RelatedWork from '../components/RelatedWork'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const DOI_LIKE = /^10\.\d{4,9}\/\S+$/i
const DOI_PREFIXES = [
  'doi:',
  'https://doi.org/',
  'http://doi.org/',
  'https://dx.doi.org/',
  'http://dx.doi.org/',
]
const PMID_PREFIXED = /^pmid:?\s*(\d{1,8})$/i

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

// Mirrors the backend normalizer: unwrap doi.org / doi: forms, strip trailing
// list punctuation (embedded semicolons in legacy Wiley DOIs are kept), and
// lowercase (DOIs are case-insensitive by spec).
function normalizeDoi(token: string): string | null {
  let t = token.trim()
  const lower = t.toLowerCase()
  for (const prefix of DOI_PREFIXES) {
    if (lower.startsWith(prefix)) {
      t = t.slice(prefix.length)
      break
    }
  }
  t = t.replace(/[.,;:]+$/, '')
  return DOI_LIKE.test(t) ? t.toLowerCase() : null
}

// Mirrors the backend heuristic: pmid:-prefixed numbers always count; a bare
// 4-digit number in the publication-year range is ambiguous (CSV year columns)
// and is not treated as a PMID.
function pmidFromToken(token: string): string | null {
  const prefixed = PMID_PREFIXED.exec(token)
  if (prefixed) return prefixed[1]
  if (!/^\d{1,8}$/.test(token)) return null
  const year = Number(token)
  if (token.length === 4 && year >= 1500 && year <= 2099) return null
  return token
}

function parseIdentifiers(text: string): { dois: string[]; pmids: string[] } {
  const dois: string[] = []
  const pmids: string[] = []
  // Split on whitespace and commas only — semicolons appear inside legacy DOIs.
  for (const token of text.split(/[\s,]+/)) {
    const t = token.trim()
    if (!t) continue
    const doi = normalizeDoi(t)
    if (doi) {
      dois.push(doi)
      continue
    }
    const pmid = pmidFromToken(t)
    if (pmid) pmids.push(pmid)
  }
  return {
    dois: Array.from(new Set(dois)),
    pmids: Array.from(new Set(pmids)),
  }
}

function stanceCount(member: CollectionMemberView, stance: string): number {
  return member.citation_tallies?.by_stance[stance] ?? 0
}

function sortMembers(
  members: CollectionMemberView[],
  sortKey: string,
): CollectionMemberView[] {
  const byAddedAsc = (a: CollectionMemberView, b: CollectionMemberView) =>
    a.added_at.localeCompare(b.added_at)
  const sorted = [...members]
  if (sortKey === 'added_asc') return sorted.sort(byAddedAsc)
  if (sortKey === 'support_desc') {
    return sorted.sort(
      (a, b) => stanceCount(b, 'support') - stanceCount(a, 'support') || byAddedAsc(b, a),
    )
  }
  if (sortKey === 'contradict_desc') {
    return sorted.sort(
      (a, b) =>
        stanceCount(b, 'contradict') - stanceCount(a, 'contradict') || byAddedAsc(b, a),
    )
  }
  return sorted.sort((a, b) => byAddedAsc(b, a))
}

// RFC 4180 quoting for every cell, plus a guard against spreadsheet formula
// injection for values starting with =, +, -, @, or a tab.
function csvCell(value: string): string {
  const guarded = /^[=+\-@\t]/.test(value) ? `'${value}` : value
  return `"${guarded.replaceAll('"', '""')}"`
}

function downloadBlob(content: string, mimeType: string, filename: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
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
        `/collections/${collectionId}?include_member_tallies=true`,
      ),
    [collectionId],
  )
  const delta = useApi<CollectionCitationDelta>(
    () =>
      api.get<CollectionCitationDelta>(
        `/collections/${collectionId}/new-citations`,
      ),
    [collectionId],
  )
  const [csvText, setCsvText] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [importing, setImporting] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savingMeta, setSavingMeta] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [watchBusy, setWatchBusy] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const parsed = parseIdentifiers(csvText)
  const normalizedFilter = memberFilter.trim().toLowerCase()
  const filteredMembers = detail.data?.members.filter((member) => {
    if (!normalizedFilter) return true
    return [member.title, member.doi, member.pmid, member.work_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedFilter))
  }) ?? []
  const visibleMembers = sortMembers(filteredMembers, memberSort)

  const loadedCollectionId = detail.data?.collection_id
  useEffect(() => {
    // Populate the metadata form only when a (different) collection loads, so
    // refetches after member changes don't clobber in-progress edits.
    if (!detail.data) return
    setName(detail.data.name)
    setDescription(detail.data.description ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedCollectionId])

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

  // Reference-manager import (WP9): read a Zotero/Mendeley RIS or BibTeX export,
  // let the backend parse it to identifiers, and seed the collection directly.
  async function onImportLibrary(file: File | null) {
    if (!file) return
    setImporting(true)
    setError(null)
    setMessage(null)
    try {
      const text = await readFileText(file)
      const lower = file.name.toLowerCase()
      const format = lower.endsWith('.ris')
        ? 'ris'
        : lower.endsWith('.bib') || lower.endsWith('.bibtex')
          ? 'bibtex'
          : undefined
      const result = await api.post<CollectionImportResult>(
        `/collections/${collectionId}/import`,
        { text, format },
      )
      const stubCount = result.created_stub_work_ids.length
      const skippedCount = result.skipped_identifiers.length
      setMessage(
        `Imported ${result.matched_count} of ${result.entry_count} ` +
          `${result.format.toUpperCase()} reference(s): added ${result.added_count} member(s)` +
          (stubCount ? `; ${stubCount} created as metadata stubs` : '') +
          (skippedCount ? `; ${skippedCount} skipped` : '') +
          '.',
      )
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setImporting(false)
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

  async function onToggleWatch() {
    const next = !detail.data?.is_watched
    setWatchBusy(true)
    setError(null)
    setMessage(null)
    try {
      await api.post(`/collections/${collectionId}/watch`, { watch: next })
      setMessage(
        next
          ? 'Now watching this collection. New-citation baseline captured.'
          : 'Stopped watching this collection.',
      )
      detail.reload()
      delta.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setWatchBusy(false)
    }
  }

  async function onBulkRemove() {
    if (visibleMembers.length === 0) return
    if (
      !window.confirm(
        `Remove ${visibleMembers.length} member(s) matching the current filter?`,
      )
    ) {
      return
    }
    setBulkBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<{ removed_count: number }>(
        `/collections/${collectionId}/members/bulk-delete`,
        { work_ids: visibleMembers.map((member) => member.work_id) },
      )
      setMessage(`Removed ${result.removed_count} member(s).`)
      detail.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBulkBusy(false)
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
    if (visibleMembers.length === 0) return
    const lines = ['work_id,doi,pmid,title,is_retracted,integrity_notice']
    for (const member of visibleMembers) {
      lines.push(
        [
          csvCell(member.work_id),
          csvCell(member.doi ?? ''),
          csvCell(member.pmid ?? ''),
          csvCell(member.title ?? ''),
          csvCell(member.is_retracted ? 'true' : ''),
          csvCell(member.integrity_notice ?? ''),
        ].join(','),
      )
    }
    downloadBlob(
      lines.join('\n') + '\n',
      'text/csv;charset=utf-8',
      `${collectionId}-members.csv`,
    )
  }

  function onExportIdentifiersTxt() {
    if (visibleMembers.length === 0) return
    const ids = Array.from(
      new Set(
        visibleMembers.flatMap((member) => [member.doi, member.pmid]).filter(Boolean),
      ),
    )
    if (ids.length === 0) return
    downloadBlob(
      ids.join('\n') + '\n',
      'text/plain;charset=utf-8',
      `${collectionId}-identifiers.txt`,
    )
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
          {detail.data.members.length > 0 && (
            <div className="margin-top-2 margin-bottom-2">
              <Link
                className="usa-button usa-button--outline"
                to={`/analytics?collection=${collectionId}`}
              >
                Analyze these papers
              </Link>
              <Link
                className="usa-button usa-button--outline margin-left-1"
                to={`/graph?collection=${collectionId}`}
              >
                Explore as network
              </Link>
            </div>
          )}
          <section className="usa-summary-box margin-bottom-2" aria-labelledby="monitoring-heading">
            <div className="usa-summary-box__body">
              <h2 className="usa-summary-box__heading" id="monitoring-heading">
                Monitoring
              </h2>
              <div className="usa-summary-box__text">
                <button
                  type="button"
                  className={
                    detail.data.is_watched
                      ? 'usa-button usa-button--outline'
                      : 'usa-button'
                  }
                  onClick={onToggleWatch}
                  disabled={watchBusy}
                  aria-pressed={detail.data.is_watched}
                >
                  {detail.data.is_watched
                    ? 'Watching ✓ — stop watching'
                    : 'Watch this collection'}
                </button>
                {delta.data?.has_snapshot ? (
                  <div className="margin-top-2" aria-live="polite">
                    <p className="margin-y-05">
                      New since baseline:{' '}
                      <strong>{delta.data.new_support_total}</strong> supporting,{' '}
                      <strong>{delta.data.new_contradict_total}</strong> contradicting.
                    </p>
                    {delta.data.members.length > 0 ? (
                      <ul className="usa-list">
                        {delta.data.members.map((row) => (
                          <li key={row.work_id}>
                            <Link to={`/papers/${row.work_id}`}>
                              {row.title ?? row.work_id}
                            </Link>{' '}
                            — +{row.new_support} supporting, +{row.new_contradict}{' '}
                            contradicting
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-base margin-y-05">
                        No new citation signals since the last baseline.
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-base margin-top-1 margin-bottom-0">
                    Start watching to capture a baseline and track new supporting
                    or contradicting citations.
                  </p>
                )}
              </div>
            </div>
          </section>

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

          <h2>Import from a reference manager</h2>
          <p className="font-body-3xs text-base margin-top-0">
            Upload a Zotero or Mendeley export (RIS or BibTeX). DOIs and PMIDs are
            extracted and added as members automatically.
          </p>
          <label className="usa-label" htmlFor="library-file">Upload RIS/BibTeX</label>
          <input
            id="library-file"
            className="usa-file-input"
            type="file"
            accept=".ris,.bib,.bibtex,application/x-research-info-systems,application/x-bibtex"
            disabled={importing}
            onChange={(e) => {
              const input = e.currentTarget
              const file = input.files?.[0] ?? null
              // Reset so re-selecting the same file fires another change event.
              input.value = ''
              void onImportLibrary(file)
            }}
          />
          {importing && (
            <p className="font-body-3xs text-base margin-top-05 margin-bottom-0">
              Importing library…
            </p>
          )}

          {detail.data.members.length > 0 && (
            <section
              className="usa-summary-box margin-y-2"
              aria-labelledby="grow-heading"
            >
              <div className="usa-summary-box__body">
                <h2 className="usa-summary-box__heading" id="grow-heading">
                  Grow this collection
                </h2>
                <div className="usa-summary-box__text">
                  <p className="margin-top-0">
                    Find papers connected to this collection through shared
                    references (Semantic Scholar), based on up to 25 of its members.
                  </p>
                  <RelatedWork
                    seedWorkIds={detail.data.members
                      .slice(0, 25)
                      .map((member) => member.work_id)}
                    label="Find related work"
                  />
                </div>
              </div>
            </section>
          )}

          <h2>Batch add members</h2>
          <p className="font-body-3xs text-base margin-top-0">
            Paste DOIs and PMIDs (comma, whitespace, or newline separated).
          </p>
          <label className="usa-label" htmlFor="identifiers-file">Upload CSV/TXT</label>
          <input
            id="identifiers-file"
            className="usa-file-input"
            type="file"
            accept=".csv,.txt,text/csv,text/plain"
            onChange={(e) => {
              const input = e.currentTarget
              const file = input.files?.[0] ?? null
              // Reset so re-selecting the same file fires another change event.
              input.value = ''
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
              placeholder={'10.1000/example-doi\n12345678'}
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
                <button
                  type="button"
                  className="usa-button usa-button--secondary margin-top-1 margin-left-1"
                  onClick={onBulkRemove}
                  disabled={bulkBusy || visibleMembers.length === 0}
                >
                  {bulkBusy
                    ? 'Removing…'
                    : `Remove ${visibleMembers.length} filtered member(s)`}
                </button>
                <p className="font-body-3xs text-base margin-top-05 margin-bottom-0">
                  Exports and bulk removal apply only to the members matching the
                  current filter.
                </p>
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
                {visibleMembers.map((member) => (
                  <tr key={member.collection_membership_id}>
                    <td>
                      <Link to={`/papers/${member.work_id}`}>
                        {member.title ?? member.work_id}
                      </Link>
                      <IntegrityBadges
                        isRetracted={member.is_retracted}
                        integrityNotice={member.integrity_notice}
                        className="margin-left-1"
                      />
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
              {visibleMembers.length === 0 && (
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
