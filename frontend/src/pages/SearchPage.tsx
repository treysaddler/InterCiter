import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { SavedSearchView, SearchResults } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageHeading from '../components/PageHeading'
import SearchBox from '../components/SearchBox'
import { Loading, ErrorAlert } from '../components/States'
import { EXAMPLE_QUERIES } from '../data/exampleQueries'
import { useApi } from '../hooks/useApi'

// The network view pulls in the d3 SVG renderer so it is code-split and only fetched
// once a search has results to explore.
const SearchNetwork = lazy(() => import('../components/SearchNetwork'))

/** Facet params that narrow a query (kept separate from the free-text `q`). */
const FACET_KEYS = ['section', 'function', 'stance', 'resolution'] as const
type FacetKey = (typeof FACET_KEYS)[number]

const FACET_LABELS: Record<FacetKey, string> = {
  section: 'Section',
  function: 'Function',
  stance: 'Stance',
  resolution: 'Resolution',
}

/**
 * Full-text claim search (scite-parity F3). Consumes GET /v1/search/claims.
 *
 * Search is the primary surface: a big box, faceted narrowing built from the live
 * facet counts, and result cards that keep every claim anchored to its source span —
 * with function and stance shown as SEPARATE tags, never a blended label.
 */
export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''

  const activeFacets = FACET_KEYS.filter((k) => params.get(k))
  const hasQuery = q.trim().length > 0 || activeFacets.length > 0

  const query = params.toString()
  const results = useApi<SearchResults | null>(
    () =>
      hasQuery
        ? api.get<SearchResults>(`/search/claims?${query}`)
        : Promise.resolve(null),
    [query, hasQuery],
  )

  // The paper whose citation network is shown inline. Defaults to the top result so a
  // network appears with the results; a reader can re-focus it on any other hit.
  const [focusWorkId, setFocusWorkId] = useState<string | null>(null)
  const hits = results.data?.hits ?? []
  const hitWorkKey = hits.map((h) => h.work_id).join(',')
  useEffect(() => {
    if (hits.length === 0) {
      setFocusWorkId(null)
      return
    }
    setFocusWorkId((current) =>
      current && hits.some((h) => h.work_id === current) ? current : hits[0].work_id,
    )
    // Re-evaluate only when the set of result papers changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hitWorkKey])

  const focusTitle =
    hits.find((h) => h.work_id === focusWorkId)?.paper_title ?? null

  const { status } = useAuth()
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onSaveSearch() {
    setSaving(true)
    setSaveMessage(null)
    try {
      const name = q.trim() || activeFacets.map((k) => params.get(k)).join(' · ') || 'Saved search'
      await api.post<SavedSearchView>('/saved-searches', {
        name,
        query: {
          q,
          section: params.get('section'),
          function: params.get('function'),
          stance: params.get('stance'),
          resolution: params.get('resolution'),
        },
      })
      setSaveMessage('Saved. Track new matches on the Alerts page.')
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  function toggleFacet(key: FacetKey, value: string) {
    const next = new URLSearchParams(params)
    if (next.get(key) === value) next.delete(key)
    else next.set(key, value)
    setParams(next)
  }

  function clearFacets() {
    const next = new URLSearchParams()
    if (q) next.set('q', q)
    setParams(next)
  }

  return (
    <>
      <PageHeading>Search claims</PageHeading>
      <p className="usa-intro measure-4">
        Search inside citation statements — every result stays anchored to the exact
        sentence it came from.
      </p>

      <div className="margin-top-2 measure-5">
        <SearchBox initialQuery={q} big extraParams={facetOnly(params)} autoFocus />
      </div>

      {!hasQuery && (
        <section className="margin-top-4" aria-label="Example searches">
          <h2 className="font-heading-sm">Try an example</h2>
          <ul className="usa-list usa-list--unstyled">
            {EXAMPLE_QUERIES.map((ex) => (
              <li key={ex.to} className="margin-bottom-1">
                <Link to={ex.to}>{ex.label}</Link>
                <span className="font-body-3xs text-base"> — {ex.hint}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {hasQuery && results.loading && <Loading label="Searching…" />}
      {hasQuery && results.error && <ErrorAlert message={results.error} />}

      {hasQuery && results.data && (
        <div className="grid-row grid-gap margin-top-3">
          <div className="grid-col-12 tablet:grid-col-4">
            <FacetPanel
              results={results.data}
              params={params}
              onToggle={toggleFacet}
              onClear={clearFacets}
              activeCount={activeFacets.length}
            />
          </div>

          <div className="grid-col-12 tablet:grid-col-8">
            <p className="text-base" role="status">
              {results.data.total === 0
                ? 'No claims matched.'
                : `${results.data.total} matching claim${
                    results.data.total === 1 ? '' : 's'
                  }`}
            </p>

            {status === 'authenticated' && (
              <p className="margin-top-0">
                <button
                  type="button"
                  className="usa-button usa-button--outline"
                  onClick={onSaveSearch}
                  disabled={saving}
                >
                  {saving ? 'Saving…' : 'Save this search'}
                </button>
                {saveMessage && (
                  <span className="margin-left-1 text-base">
                    {saveMessage}{' '}
                    <Link to="/alerts">Go to Alerts</Link>
                  </span>
                )}
              </p>
            )}

            {focusWorkId && (
              <Suspense fallback={<Loading label="Loading network…" />}>
                <SearchNetwork
                  workId={focusWorkId}
                  title={focusTitle}
                  onFocusPaper={setFocusWorkId}
                />
              </Suspense>
            )}

            <ol className="usa-list usa-list--unstyled">
              {results.data.hits.map((hit) => (
                <li
                  key={hit.claim_id}
                  className="margin-bottom-3 padding-bottom-2 border-bottom border-base-lighter"
                >
                  <Link
                    to={`/claims/${hit.claim_id}`}
                    className="font-body-md text-bold"
                  >
                    {hit.normalized_text}
                  </Link>

                  <p className="font-body-3xs text-base margin-y-05">
                    {hit.paper_title ? (
                      <Link to={`/papers/${hit.work_id}`}>{hit.paper_title}</Link>
                    ) : (
                      <Link to={`/papers/${hit.work_id}`}>{hit.work_id}</Link>
                    )}
                    {hit.year != null && <span> · {hit.year}</span>}
                    {hit.section && <span> · {hit.section}</span>}
                  </p>

                  <blockquote className="margin-0 padding-left-1 border-left-05 border-base-lighter font-body-2xs text-base-dark">
                    “{hit.evidence.verbatim_text}”
                  </blockquote>

                  {(hit.function.length > 0 || hit.stance.length > 0) && (
                    <p className="margin-top-1">
                      {hit.function.map((f) => (
                        <span
                          key={`fn-${f}`}
                          className="usa-tag bg-accent-cool-lighter text-ink margin-right-1 text-no-uppercase"
                        >
                          {f.replace(/_/g, ' ')}
                        </span>
                      ))}
                      {hit.stance.map((s) => (
                        <span
                          key={`st-${s}`}
                          className="usa-tag bg-primary-lighter text-ink margin-right-1 text-no-uppercase"
                        >
                          {s}
                        </span>
                      ))}
                    </p>
                  )}

                  <p className="margin-top-1 margin-bottom-0">
                    {focusWorkId === hit.work_id ? (
                      <span className="font-body-3xs text-base">
                        ✓ Shown in the network above
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="usa-button usa-button--unstyled font-body-3xs"
                        onClick={() => setFocusWorkId(hit.work_id)}
                      >
                        Focus this paper in the network
                      </button>
                    )}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </>
  )
}

/** The subset of params that are facets (used to preserve them across a new search). */
function facetOnly(params: URLSearchParams): URLSearchParams {
  const out = new URLSearchParams()
  for (const key of FACET_KEYS) {
    const value = params.get(key)
    if (value) out.set(key, value)
  }
  return out
}

function FacetPanel({
  results,
  params,
  onToggle,
  onClear,
  activeCount,
}: {
  results: SearchResults
  params: URLSearchParams
  onToggle: (key: FacetKey, value: string) => void
  onClear: () => void
  activeCount: number
}) {
  return (
    <div className="usa-prose">
      <div className="display-flex flex-align-center flex-justify">
        <h2 className="font-heading-sm margin-0">Filters</h2>
        {activeCount > 0 && (
          <button
            type="button"
            className="usa-button usa-button--unstyled font-body-3xs"
            onClick={onClear}
          >
            Clear ({activeCount})
          </button>
        )}
      </div>

      {FACET_KEYS.map((key) => {
        const counts = results.facets[key]
        const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
        if (entries.length === 0) return null
        const active = params.get(key)
        return (
          <fieldset key={key} className="usa-fieldset margin-top-2">
            <legend className="usa-legend font-body-3xs text-bold text-uppercase text-base">
              {FACET_LABELS[key]}
            </legend>
            <ul className="usa-list usa-list--unstyled">
              {entries.map(([value, count]) => (
                <li key={value}>
                  <button
                    type="button"
                    className={`usa-button usa-button--unstyled text-no-underline${
                      active === value ? ' text-bold' : ''
                    }`}
                    aria-pressed={active === value}
                    onClick={() => onToggle(key, value)}
                  >
                    {active === value ? '✓ ' : ''}
                    {value.replace(/_/g, ' ')}{' '}
                    <span className="text-base">({count})</span>
                  </button>
                </li>
              ))}
            </ul>
          </fieldset>
        )
      })}
    </div>
  )
}
