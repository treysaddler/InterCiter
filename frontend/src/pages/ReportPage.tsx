import { useEffect, useState } from 'react'
import { Link, useSearchParams, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { PaperReport } from '../api/types'
import CitationTallies from '../components/CitationTallies'
import PageHeading from '../components/PageHeading'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const YEAR_DEBOUNCE_MS = 400

function humanize(value: string): string {
  const spaced = value.replaceAll('_', ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

// Options come from the report's unfiltered facet counts, so they always match
// the backend's live enum values; the applied value is kept selectable even if
// it no longer matches any statement.
function facetOptions(counts: Record<string, number>, current: string): string[] {
  const values = Object.keys(counts)
  if (current && !values.includes(current)) values.push(current)
  return values.sort()
}

/**
 * Per-paper citation report (scite-parity WP3): tallies + timeline + conflicts
 * + filterable citing statements.
 */
export default function ReportPage() {
  const { workId = '' } = useParams()
  const [params, setParams] = useSearchParams()

  const query = new URLSearchParams()
  for (const key of ['section', 'function', 'stance', 'resolution', 'min_year', 'max_year']) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  const endpoint = `/papers/${workId}/report${query.toString() ? `?${query.toString()}` : ''}`

  const report = useApi<PaperReport>(() => api.get<PaperReport>(endpoint), [endpoint])

  // Year bounds are edited locally and pushed to the URL after a debounce so
  // each keystroke doesn't refetch the report.
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
      if (next.toString() !== params.toString()) setParams(next)
    }, YEAR_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [minYear, maxYear, params, setParams])

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
  }

  return (
    <>
      <p className="margin-top-4 margin-bottom-0">
        <Link to={`/papers/${workId}`}>← Paper</Link>
      </p>
      <PageHeading>Citation report</PageHeading>

      {report.loading && <Loading />}
      {report.error && <ErrorAlert message={report.error} />}

      {report.data && (
        <>
          <p className="text-base margin-top-0">
            {report.data.filtered_statements} of {report.data.total_statements} citing statements shown.
          </p>

          <h2 className="margin-top-4">Filter statements</h2>
          <div className="grid-row grid-gap">
            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-stance">Stance</label>
              <select
                id="report-stance"
                className="usa-select"
                value={params.get('stance') ?? ''}
                onChange={(e) => updateFilter('stance', e.target.value)}
              >
                <option value="">All stances</option>
                {facetOptions(report.data.facets.stance, params.get('stance') ?? '').map(
                  (value) => (
                    <option key={value} value={value}>{humanize(value)}</option>
                  ),
                )}
              </select>
            </div>

            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-function">Function</label>
              <select
                id="report-function"
                className="usa-select"
                value={params.get('function') ?? ''}
                onChange={(e) => updateFilter('function', e.target.value)}
              >
                <option value="">All functions</option>
                {facetOptions(report.data.facets.function, params.get('function') ?? '').map(
                  (value) => (
                    <option key={value} value={value}>{humanize(value)}</option>
                  ),
                )}
              </select>
            </div>

            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-resolution">Resolution</label>
              <select
                id="report-resolution"
                className="usa-select"
                value={params.get('resolution') ?? ''}
                onChange={(e) => updateFilter('resolution', e.target.value)}
              >
                <option value="">All resolutions</option>
                {facetOptions(report.data.facets.resolution, params.get('resolution') ?? '').map(
                  (value) => (
                    <option key={value} value={value}>{humanize(value)}</option>
                  ),
                )}
              </select>
            </div>

            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-section">Section</label>
              <select
                id="report-section"
                className="usa-select"
                value={params.get('section') ?? ''}
                onChange={(e) => updateFilter('section', e.target.value)}
              >
                <option value="">All sections</option>
                {facetOptions(report.data.facets.section, params.get('section') ?? '').map(
                  (name) => (
                    <option key={name} value={name}>{name}</option>
                  ),
                )}
              </select>
            </div>
          </div>

          <div className="grid-row grid-gap margin-top-2">
            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-min-year">Min year</label>
              <input
                id="report-min-year"
                className="usa-input"
                inputMode="numeric"
                value={minYear}
                onChange={(e) => setMinYear(e.target.value.replace(/[^0-9]/g, ''))}
              />
            </div>
            <div className="tablet:grid-col-3">
              <label className="usa-label" htmlFor="report-max-year">Max year</label>
              <input
                id="report-max-year"
                className="usa-input"
                inputMode="numeric"
                value={maxYear}
                onChange={(e) => setMaxYear(e.target.value.replace(/[^0-9]/g, ''))}
              />
            </div>
          </div>

          <h2 className="margin-top-4">How this paper has been cited</h2>
          <CitationTallies tallies={report.data.tallies} />

          <h2 className="margin-top-4">Conflicting stance summary</h2>
          <ul className="usa-list usa-list--unstyled">
            <li>
              <strong>Conflict present:</strong>{' '}
              {report.data.conflict_summary.has_conflicting_stances ? 'yes' : 'no'}
            </li>
            <li><strong>Supporting statements:</strong> {report.data.conflict_summary.supporting_statements}</li>
            <li><strong>Contradicting statements:</strong> {report.data.conflict_summary.contradicting_statements}</li>
            <li><strong>Neutral/unclear statements:</strong> {report.data.conflict_summary.neutral_or_unclear_statements}</li>
          </ul>

          <h2 className="margin-top-4">Citations over time</h2>
          {report.data.timeline.length === 0 ? (
            <Empty>No citing-year data available for timeline buckets.</Empty>
          ) : (
            <table className="usa-table usa-table--borderless width-full">
              <caption className="usa-sr-only">Citation timeline by year</caption>
              <thead>
                <tr>
                  <th scope="col">Year</th>
                  <th scope="col">Citing works</th>
                  <th scope="col">Statements</th>
                </tr>
              </thead>
              <tbody>
                {report.data.timeline.map((point) => (
                  <tr key={point.year}>
                    <td>{point.year}</td>
                    <td>{point.citing_work_count}</td>
                    <td>{point.statement_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="margin-top-4">Citing statements</h2>
          {report.data.statements.length === 0 && <Empty>No statements match the current filters.</Empty>}
          {report.data.statements.length > 0 && (
            <ol className="usa-list">
              {report.data.statements.map((statement) => (
                <li key={statement.assertion_id} className="margin-bottom-2">
                  <p className="margin-y-0">
                    <strong>Stance:</strong> {statement.stance ?? 'abstained'} ·{' '}
                    <strong>Function:</strong> {statement.function ?? 'abstained'} ·{' '}
                    <strong>Section:</strong> {statement.section ?? 'unspecified'}
                  </p>
                  {statement.evidence?.verbatim_text && (
                    <p className="font-body-3xs margin-top-05 margin-bottom-0">
                      “{statement.evidence.verbatim_text.slice(0, 280)}{statement.evidence.verbatim_text.length > 280 ? '…' : ''}”
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </>
  )
}
