import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { BibliometricsSummary } from '../api/types'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const YEAR_DEBOUNCE_MS = 400

/** One "Main Information" indicator card. */
function Indicator({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="usa-card__container radius-md padding-2 border-1px border-base-lighter">
      <p className="margin-0 text-base-dark font-body-2xs text-uppercase">{label}</p>
      <p className="margin-0 margin-top-1 font-heading-lg text-bold">{value}</p>
    </div>
  )
}

/**
 * Corpus descriptive analytics — bibliometrix "Main Information" dashboard
 * (bibliometrix-parity WP-B1). Consumes GET /v1/bibliometrics/summary. Reads are
 * open (no auth). Optional year bounds narrow the cohort.
 *
 * Every visualization keeps an accessible table as the source of truth; the annual
 * production bars are decorative (aria-hidden) alongside the table.
 */
export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams()

  const query = new URLSearchParams()
  for (const key of ['min_year', 'max_year']) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  const endpoint = `/bibliometrics/summary${query.toString() ? `?${query.toString()}` : ''}`

  const { data, error, loading } = useApi<BibliometricsSummary>(
    () => api.get<BibliometricsSummary>(endpoint),
    [endpoint],
  )

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

  const maxAnnual = data
    ? Math.max(1, ...data.annual_production.map((p) => p.document_count))
    : 1

  return (
    <>
      <PageHeading>Analytics</PageHeading>
      <p className="usa-intro font-body-md">
        Corpus-level "Main Information" — descriptive statistics over the whole
        collection's metadata (bibliometrix). This is the aggregate metadata lens that
        complements InterCiter's claim-level function, stance, and provenance.
      </p>

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

      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}

      {data && data.document_count === 0 && (
        <Empty>
          No documents match this cohort. <Link to="/ingest">Submit a paper</Link> or
          widen the year range.
        </Empty>
      )}

      {data && data.document_count > 0 && (
        <>
          <h2>Main information</h2>
          <ul className="usa-card-group">
            {[
              { label: 'Timespan', value:
                data.min_year && data.max_year
                  ? `${data.min_year}–${data.max_year}`
                  : '—' },
              { label: 'Documents', value: data.document_count },
              { label: 'Sources', value: data.source_count },
              { label: 'Authors', value: data.author_count },
              { label: 'Co-authors / doc', value: data.co_authors_per_doc },
              { label: 'Single-authored docs', value: data.single_authored_count },
              {
                label: 'Annual growth rate',
                value:
                  data.annual_growth_rate === null
                    ? '—'
                    : `${data.annual_growth_rate}%`,
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
              {data.top_authors.length === 0 ? (
                <Empty>No author metadata.</Empty>
              ) : (
                <table className="usa-table usa-table--borderless width-full">
                  <thead>
                    <tr>
                      <th scope="col">Author</th>
                      <th scope="col">Documents</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_authors.map((a) => (
                      <tr key={a.name}>
                        <td>{a.name}</td>
                        <td>{a.document_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="tablet:grid-col-6">
              <h2>Most relevant sources</h2>
              {data.top_sources.length === 0 ? (
                <Empty>No source metadata.</Empty>
              ) : (
                <table className="usa-table usa-table--borderless width-full">
                  <thead>
                    <tr>
                      <th scope="col">Source</th>
                      <th scope="col">Documents</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_sources.map((s) => (
                      <tr key={s.source}>
                        <td>{s.source}</td>
                        <td>{s.document_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
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
      )}
    </>
  )
}
