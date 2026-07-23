import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type {
  AuthorMetrics,
  BibliometricsSummary,
  CountryMetrics,
  SourceMetrics,
} from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const YEAR_DEBOUNCE_MS = 400

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'authors', label: 'Authors' },
  { key: 'sources', label: 'Sources' },
  { key: 'countries', label: 'Countries' },
] as const

type TabKey = (typeof TABS)[number]['key']

/**
 * Build the shared query string forwarded to every bibliometrics endpoint: the
 * year bounds plus the cohort selector. The cohort can be a saved `collection` or
 * `map` (resolved by reference server-side, UX-3) or an explicit `work_ids` set.
 */
function cohortQuery(params: URLSearchParams): string {
  const query = new URLSearchParams()
  for (const key of ['min_year', 'max_year', 'collection', 'map']) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  for (const workId of params.getAll('work_ids')) query.append('work_ids', workId)
  return query.toString() ? `?${query.toString()}` : ''
}

/**
 * When analytics is scoped to a saved collection or map, show which cohort is
 * active and a way back to the whole corpus. The name is fetched best-effort
 * (owner-scoped cohorts require the viewer to be signed in).
 */
function CohortBanner({
  collection,
  map,
}: {
  collection: string | null
  map: string | null
}) {
  const type = collection ? 'collection' : map ? 'map' : null
  const path = collection
    ? `/collections/${collection}`
    : map
      ? `/maps/${map}`
      : null
  const meta = useApi<{ name: string } | null>(
    () => (path ? api.get<{ name: string }>(path) : Promise.resolve(null)),
    [path],
  )
  if (!type) return null
  const name = meta.data?.name
  return (
    <div
      className="usa-alert usa-alert--info usa-alert--slim margin-bottom-2"
      role="status"
    >
      <div className="usa-alert__body">
        <p className="usa-alert__text">
          Analyzing a saved {type}
          {name ? (
            <>
              : <strong>{name}</strong>
            </>
          ) : null}
          . <Link to="/analytics">Analyze the full corpus</Link>
        </p>
      </div>
    </div>
  )
}

/** One "Main Information" indicator card. */
function Indicator({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="usa-card__container radius-md padding-2 border-1px border-base-lighter">
      <p className="margin-0 text-base-dark font-body-2xs text-uppercase">{label}</p>
      <p className="margin-0 margin-top-1 font-heading-lg text-bold">{value}</p>
    </div>
  )
}

/** A generic accessible rank table used by every metric panel. */
function RankTable<T>({
  rows,
  columns,
  cells,
  rowKey,
  empty,
}: {
  rows: T[]
  columns: string[]
  cells: (row: T) => (string | number)[]
  rowKey: (row: T) => string
  empty: string
}) {
  if (rows.length === 0) return <Empty>{empty}</Empty>
  return (
    <table className="usa-table usa-table--borderless width-full">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c} scope="col">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {cells(row).map((value, i) => (
              <td key={columns[i]}>{value}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function OverviewPanel({ suffix }: { suffix: string }) {
  const { data, error, loading } = useApi<BibliometricsSummary>(
    () => api.get<BibliometricsSummary>(`/bibliometrics/summary${suffix}`),
    [suffix],
  )

  const maxAnnual = data
    ? Math.max(1, ...data.annual_production.map((p) => p.document_count))
    : 1

  if (loading) return <Loading />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null
  if (data.document_count === 0) {
    return (
      <Empty>
        No documents match this cohort. <Link to="/ingest">Submit a paper</Link> or
        widen the year range.
      </Empty>
    )
  }

  return (
    <>
      <h2>Main information</h2>
      <ul className="usa-card-group">
        {[
          {
            label: 'Timespan',
            value:
              data.min_year && data.max_year ? `${data.min_year}–${data.max_year}` : '—',
          },
          { label: 'Documents', value: data.document_count },
          { label: 'Sources', value: data.source_count },
          { label: 'Authors', value: data.author_count },
          { label: 'Co-authors / doc', value: data.co_authors_per_doc },
          { label: 'Single-authored docs', value: data.single_authored_count },
          {
            label: 'Annual growth rate',
            value: data.annual_growth_rate === null ? '—' : `${data.annual_growth_rate}%`,
          },
          { label: 'Avg citations / doc', value: data.avg_citations_per_doc },
          { label: 'Total citations', value: data.total_citations },
        ].map((card) => (
          <li key={card.label} className="usa-card tablet:grid-col-4 desktop:grid-col-3">
            <Indicator label={card.label} value={card.value} />
          </li>
        ))}
      </ul>

      <h2>Annual scientific production</h2>
      {data.annual_production.length === 0 ? (
        <Empty>No dated documents in this cohort.</Empty>
      ) : (
        <table className="usa-table usa-table--borderless width-full">
          <caption className="usa-sr-only">
            Number of documents published per year.
          </caption>
          <thead>
            <tr>
              <th scope="col">Year</th>
              <th scope="col">Documents</th>
              <th scope="col">Production</th>
            </tr>
          </thead>
          <tbody>
            {data.annual_production.map((p) => (
              <tr key={p.year}>
                <th scope="row">{p.year}</th>
                <td>{p.document_count}</td>
                <td>
                  <span
                    aria-hidden="true"
                    className="display-inline-block bg-primary height-105 radius-sm"
                    style={{
                      width: `${(p.document_count / maxAnnual) * 100}%`,
                      minWidth: p.document_count > 0 ? '2px' : 0,
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="grid-row grid-gap">
        <div className="tablet:grid-col-6">
          <h2>Most productive authors</h2>
          <RankTable
            rows={data.top_authors}
            columns={['Author', 'Documents']}
            cells={(a) => [a.name, a.document_count]}
            rowKey={(a) => a.name}
            empty="No author metadata."
          />
        </div>
        <div className="tablet:grid-col-6">
          <h2>Most relevant sources</h2>
          <RankTable
            rows={data.top_sources}
            columns={['Source', 'Documents']}
            cells={(s) => [s.source, s.document_count]}
            rowKey={(s) => s.source}
            empty="No source metadata."
          />
        </div>
      </div>

      <h2>Most cited documents</h2>
      {data.top_cited_documents.length === 0 ? (
        <Empty>No citations recorded for this cohort yet.</Empty>
      ) : (
        <table className="usa-table usa-table--borderless width-full">
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Year</th>
              <th scope="col">Citations</th>
            </tr>
          </thead>
          <tbody>
            {data.top_cited_documents.map((d) => (
              <tr key={d.work_id}>
                <td>
                  <Link to={`/papers/${d.work_id}`}>{d.title ?? d.work_id}</Link>
                </td>
                <td>{d.year ?? '—'}</td>
                <td>{d.citation_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function AuthorsPanel({ suffix }: { suffix: string }) {
  const { data, error, loading } = useApi<AuthorMetrics>(
    () => api.get<AuthorMetrics>(`/bibliometrics/authors${suffix}`),
    [suffix],
  )
  if (loading) return <Loading />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null

  return (
    <>
      <h2>Most productive authors</h2>
      <p className="text-base-dark">
        {data.author_count} distinct authors. Impact is measured by document count and
        the h-index (papers with at least that many citations).
      </p>
      <RankTable
        rows={data.authors}
        columns={['Author', 'Documents', 'Citations', 'h-index']}
        cells={(a) => [a.name, a.document_count, a.total_citations, a.h_index]}
        rowKey={(a) => a.name}
        empty="No author metadata."
      />

      <h2>Author productivity (Lotka&apos;s law)</h2>
      <p className="text-base-dark">
        {data.lotka.coefficient === null
          ? 'Not enough productivity levels to fit Lotka’s law.'
          : `Fitted exponent n = ${data.lotka.coefficient}` +
            (data.lotka.constant === null ? '' : `, constant C = ${data.lotka.constant}`) +
            ' for f(x) = C / xⁿ.'}
      </p>
      <RankTable
        rows={data.lotka.points}
        columns={['Documents written', 'Authors', 'Proportion']}
        cells={(p) => [p.documents_written, p.author_count, p.proportion]}
        rowKey={(p) => String(p.documents_written)}
        empty="No author metadata."
      />
    </>
  )
}

function SourcesPanel({ suffix }: { suffix: string }) {
  const { data, error, loading } = useApi<SourceMetrics>(
    () => api.get<SourceMetrics>(`/bibliometrics/sources${suffix}`),
    [suffix],
  )
  if (loading) return <Loading />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null

  return (
    <>
      <h2>Most relevant sources</h2>
      <p className="text-base-dark">
        {data.source_count} distinct sources. Bradford&apos;s law partitions sources
        into three zones of roughly equal article totals; zone 1 is the prolific core.
      </p>
      <RankTable
        rows={data.sources}
        columns={['Source', 'Documents', 'Citations', 'h-index', 'Bradford zone']}
        cells={(s) => [
          s.source,
          s.document_count,
          s.total_citations,
          s.h_index,
          s.bradford_zone,
        ]}
        rowKey={(s) => s.source}
        empty="No source metadata."
      />

      <h2>Bradford&apos;s law zones</h2>
      <RankTable
        rows={data.bradford_zones}
        columns={['Zone', 'Sources', 'Articles']}
        cells={(z) => [z.zone, z.source_count, z.article_count]}
        rowKey={(z) => String(z.zone)}
        empty="No source metadata."
      />
    </>
  )
}

function CountriesPanel({ suffix }: { suffix: string }) {
  const { data, error, loading } = useApi<CountryMetrics>(
    () => api.get<CountryMetrics>(`/bibliometrics/countries${suffix}`),
    [suffix],
  )
  if (loading) return <Loading />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null

  if (data.documents_with_country === 0) {
    return (
      <Empty>
        No affiliation/country metadata is available for this cohort yet. Country
        analytics populate once affiliations are imported (e.g. via OpenAlex).
      </Empty>
    )
  }

  return (
    <>
      <h2>Country scientific production</h2>
      <p className="text-base-dark">
        {data.country_count} countries across {data.documents_with_country} documents
        with affiliation data.
        {data.international_co_authorship_pct !== null &&
          ` International co-authorship: ${data.international_co_authorship_pct}%.`}
      </p>
      <RankTable
        rows={data.countries}
        columns={[
          'Country',
          'Documents',
          'Single-country (SCP)',
          'Multi-country (MCP)',
          'MCP ratio',
        ]}
        cells={(c) => [
          c.country,
          c.document_count,
          c.single_country_pubs,
          c.multi_country_pubs,
          c.mcp_ratio,
        ]}
        rowKey={(c) => c.country}
        empty="No country metadata."
      />
    </>
  )
}

/**
 * Corpus descriptive analytics — bibliometrix "Main Information" + three-level
 * metrics (bibliometrix-parity WP-B1 + WP-B2). Reads are open (no auth). Tabs cover
 * the corpus overview and the author / source / country analytics (h-index, Lotka,
 * Bradford, SCP/MCP). Optional year bounds narrow the cohort across every tab.
 *
 * Every metric is presented as an accessible table (the source of truth); the annual
 * production bars are decorative (aria-hidden).
 */
export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams()
  const suffix = cohortQuery(params)
  const requestedTab = params.get('tab') as TabKey | null
  const activeTab: TabKey =
    requestedTab && TABS.some((t) => t.key === requestedTab) ? requestedTab : 'overview'

  // Year bounds are edited locally and pushed to the URL after a debounce.
  const [minYear, setMinYear] = useState(params.get('min_year') ?? '')
  const [maxYear, setMaxYear] = useState(params.get('max_year') ?? '')

  useEffect(() => {
    setMinYear(params.get('min_year') ?? '')
    setMaxYear(params.get('max_year') ?? '')
  }, [params])

  useEffect(() => {
    const handle = setTimeout(() => {
      const next = new URLSearchParams(params)
      if (minYear) next.set('min_year', minYear)
      else next.delete('min_year')
      if (maxYear) next.set('max_year', maxYear)
      else next.delete('max_year')
      if (next.toString() !== params.toString()) setParams(next, { replace: true })
    }, YEAR_DEBOUNCE_MS)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minYear, maxYear])

  function selectTab(key: TabKey) {
    const next = new URLSearchParams(params)
    if (key === 'overview') next.delete('tab')
    else next.set('tab', key)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeading>Analytics</PageHeading>
      <p className="usa-intro font-body-md">
        Corpus-level science mapping (bibliometrix) — descriptive statistics and
        three-level author / source / country metrics over the collection&apos;s
        metadata. This is the aggregate lens that complements InterCiter&apos;s
        claim-level function, stance, and provenance.
      </p>

      <CohortBanner
        collection={params.get('collection')}
        map={params.get('map')}
      />

      <form className="usa-form margin-bottom-2" onSubmit={(e) => e.preventDefault()}>
        <fieldset className="usa-fieldset">
          <legend className="usa-legend">Filter by publication year</legend>
          <div className="display-flex flex-row flex-align-end grid-gap">
            <div>
              <label className="usa-label margin-top-0" htmlFor="min-year">
                From year
              </label>
              <input
                id="min-year"
                className="usa-input width-10"
                type="number"
                inputMode="numeric"
                value={minYear}
                onChange={(e) => setMinYear(e.target.value)}
              />
            </div>
            <div>
              <label className="usa-label margin-top-0" htmlFor="max-year">
                To year
              </label>
              <input
                id="max-year"
                className="usa-input width-10"
                type="number"
                inputMode="numeric"
                value={maxYear}
                onChange={(e) => setMaxYear(e.target.value)}
              />
            </div>
          </div>
        </fieldset>
      </form>

      <nav className="usa-button-group margin-bottom-2" aria-label="Analytics views">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`usa-button ${activeTab === t.key ? '' : 'usa-button--outline'}`}
            aria-current={activeTab === t.key ? 'page' : undefined}
            onClick={() => selectTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {activeTab === 'overview' && <OverviewPanel suffix={suffix} />}
      {activeTab === 'authors' && <AuthorsPanel suffix={suffix} />}
      {activeTab === 'sources' && <SourcesPanel suffix={suffix} />}
      {activeTab === 'countries' && <CountriesPanel suffix={suffix} />}
    </>
  )
}
