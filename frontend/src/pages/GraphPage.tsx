import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { GraphExpansion, GraphNode, GraphView } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import NetworkGraph from '../components/NetworkGraph'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

type Mode = 'papers' | 'claims'

/**
 * Network exploration (docs/ui-design.md). Renders the citation/author network from
 * GET /v1/graph/papers[/:workId] and the claim network from GET /v1/graph/claims.
 * Authenticated users can grow a paper's neighborhood on demand from Semantic Scholar
 * (POST /v1/graph/papers/:workId/expand).
 */
export default function GraphPage() {
  const { workId } = useParams()
  const navigate = useNavigate()
  const { status } = useAuth()

  const [mode, setMode] = useState<Mode>('papers')
  const [includeAuthors, setIncludeAuthors] = useState(false)
  const [depth, setDepth] = useState(1)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [expanding, setExpanding] = useState(false)
  const [expandError, setExpandError] = useState<string | null>(null)

  const centered = Boolean(workId)
  const path = centered
    ? `/graph/papers/${workId}?depth=${depth}&include_authors=${includeAuthors}`
    : mode === 'papers'
      ? `/graph/papers?include_authors=${includeAuthors}`
      : `/graph/claims`

  const graph = useApi<GraphView>(() => api.get<GraphView>(path), [path])

  function onSelectNode(node: GraphNode) {
    setSelected(node)
    setNotice(null)
    setExpandError(null)
  }

  async function expandSelected() {
    if (!selected) return
    setExpanding(true)
    setExpandError(null)
    setNotice(null)
    try {
      const result = await api.post<GraphExpansion>(
        `/graph/papers/${selected.id}/expand`,
      )
      if (result.skipped_reason) {
        setNotice(`Could not expand: ${result.skipped_reason}`)
      } else {
        setNotice(
          `Added ${result.works_created} paper(s) and ${result.edges_created} citation(s) ` +
            `from ${result.references_fetched} reference(s).`,
        )
        graph.reload()
      }
    } catch (e) {
      setExpandError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setExpanding(false)
    }
  }

  return (
    <>
      {centered && (
        <p className="margin-top-4 margin-bottom-0">
          <Link to="/graph">← Full network</Link>
        </p>
      )}
      <PageHeading>{centered ? 'Paper neighborhood' : 'Explore the network'}</PageHeading>
      <p className="text-base measure-5">
        Visualize papers, authors, and how they cite one another. Select any node to
        inspect it, recenter the graph, or grow a paper&rsquo;s neighborhood from
        Semantic Scholar.
      </p>

      {/* Controls */}
      <div className="display-flex flex-wrap flex-align-center margin-y-2">
        {!centered && (
          <fieldset className="usa-fieldset margin-right-3 border-0 padding-0">
            <legend className="usa-sr-only">Network mode</legend>
            <div className="usa-button-group usa-button-group--segmented">
              <button
                type="button"
                className={`usa-button ${mode === 'papers' ? '' : 'usa-button--outline'}`}
                onClick={() => setMode('papers')}
                aria-pressed={mode === 'papers'}
              >
                Papers &amp; authors
              </button>
              <button
                type="button"
                className={`usa-button ${mode === 'claims' ? '' : 'usa-button--outline'}`}
                onClick={() => setMode('claims')}
                aria-pressed={mode === 'claims'}
              >
                Claims
              </button>
            </div>
          </fieldset>
        )}

        {(mode === 'papers' || centered) && (
          <div className="usa-checkbox margin-right-3">
            <input
              className="usa-checkbox__input"
              id="include-authors"
              type="checkbox"
              checked={includeAuthors}
              onChange={(e) => setIncludeAuthors(e.target.checked)}
            />
            <label className="usa-checkbox__label" htmlFor="include-authors">
              Show authors
            </label>
          </div>
        )}

        {centered && (
          <div>
            <label className="usa-label margin-top-0 font-body-3xs" htmlFor="depth">
              Hops
            </label>
            <select
              id="depth"
              className="usa-select width-auto"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </div>
        )}
      </div>

      {notice && (
        <div className="usa-alert usa-alert--info usa-alert--slim margin-y-2" role="status">
          <div className="usa-alert__body">
            <p className="usa-alert__text">{notice}</p>
          </div>
        </div>
      )}

      {graph.loading && <Loading label="Building graph…" />}
      {graph.error && <ErrorAlert message={graph.error} />}
      {graph.data && (
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-8">
            <NetworkGraph
              view={graph.data}
              selectedId={selected?.id}
              onSelectNode={onSelectNode}
            />
          </div>
          <div className="tablet:grid-col-4">
            <aside
              className="usa-summary-box"
              aria-label="Selected node"
            >
              <div className="usa-summary-box__body">
                {!selected && (
                  <p className="usa-summary-box__text">Select a node to see details.</p>
                )}
                {selected && (
                  <>
                    <h2 className="usa-summary-box__heading">{selected.label}</h2>
                    <p className="font-body-3xs text-base margin-top-0">
                      {selected.type}
                    </p>
                    {selected.type === 'paper' && (
                      <ul className="usa-list usa-list--unstyled">
                        <li>
                          <Link to={`/papers/${selected.id}`}>Open paper details</Link>
                        </li>
                        <li>
                          <button
                            type="button"
                            className="usa-button usa-button--unstyled"
                            onClick={() => {
                              setSelected(null)
                              navigate(`/graph/papers/${selected.id}`)
                            }}
                          >
                            Center graph here
                          </button>
                        </li>
                        <li className="margin-top-1">
                          {status === 'authenticated' ? (
                            <button
                              type="button"
                              className="usa-button usa-button--outline"
                              onClick={expandSelected}
                              disabled={expanding}
                            >
                              {expanding
                                ? 'Expanding…'
                                : 'Expand from Semantic Scholar'}
                            </button>
                          ) : (
                            <span className="font-body-3xs text-base">
                              <Link to="/login">Sign in</Link> to expand from Semantic
                              Scholar.
                            </span>
                          )}
                        </li>
                      </ul>
                    )}
                    {selected.type === 'claim' && (
                      <p>
                        <Link to={`/claims/${selected.id}`}>Open claim</Link>
                      </p>
                    )}
                    {expandError && <ErrorAlert message={expandError} />}
                  </>
                )}
              </div>
            </aside>
          </div>
        </div>
      )}
    </>
  )
}
