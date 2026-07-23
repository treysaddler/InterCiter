import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type {
  ClaimExpansion,
  GraphExpansion,
  GraphNode,
  GraphView,
  MapDetailView,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'
import NetworkGraph, {
  MEASURE_LABELS,
  type GraphMeasure,
  type LayoutMode,
} from '../components/NetworkGraph'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

type Mode = 'papers' | 'claims'

const MEASURES: GraphMeasure[] = ['year', 'cited_by_count', 'references_count']

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
  const [searchParams] = useSearchParams()
  const mapId = searchParams.get('map')

  const [mode, setMode] = useState<Mode>('papers')
  const [includeAuthors, setIncludeAuthors] = useState(false)
  const [depth, setDepth] = useState(1)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [expanding, setExpanding] = useState(false)
  const [expandError, setExpandError] = useState<string | null>(null)
  const [savingMap, setSavingMap] = useState(false)
  // Litmaps-style dynamic mapping: force layout by default, or map papers onto
  // quantitative axes (e.g. year × citation count) and size nodes by a measure.
  const [layout, setLayout] = useState<LayoutMode>('force')
  const [xMeasure, setXMeasure] = useState<GraphMeasure>('year')
  const [yMeasure, setYMeasure] = useState<GraphMeasure>('cited_by_count')
  const [sizeMeasure, setSizeMeasure] = useState<GraphMeasure | 'none'>('none')
  // A ROBOKOP claim expansion produces its own knowledge-graph view that temporarily
  // replaces the citation/claim network until the user clears it.
  const [robokopGraph, setRobokopGraph] = useState<GraphView | null>(null)

  const centered = Boolean(workId)
  const path = mapId
    ? `/maps/${mapId}/graph?include_authors=${includeAuthors}`
    : centered
      ? `/graph/papers/${workId}?depth=${depth}&include_authors=${includeAuthors}`
      : mode === 'papers'
        ? `/graph/papers?include_authors=${includeAuthors}`
        : `/graph/claims`

  const graph = useApi<GraphView>(() => api.get<GraphView>(path), [path])
  // When loading a saved map, fetch its metadata to hydrate the layout controls.
  const mapMeta = useApi<MapDetailView | null>(
    () => (mapId ? api.get<MapDetailView>(`/maps/${mapId}`) : Promise.resolve(null)),
    [mapId],
  )
  const displayed = robokopGraph ?? graph.data
  // Axis/measure layout only makes sense for the paper/citation network (paper nodes
  // carry year + citation counts); claims and ROBOKOP overlays fall back to force.
  const measureable = !robokopGraph && (Boolean(mapId) || mode === 'papers')
  const effectiveLayout: LayoutMode = measureable ? layout : 'force'

  // Hydrate layout controls from a loaded map's saved layout_config (once).
  useEffect(() => {
    const cfg = mapMeta.data?.layout_config
    if (!cfg) return
    if (cfg.layout === 'force' || cfg.layout === 'axis') setLayout(cfg.layout)
    if (typeof cfg.xMeasure === 'string') setXMeasure(cfg.xMeasure as GraphMeasure)
    if (typeof cfg.yMeasure === 'string') setYMeasure(cfg.yMeasure as GraphMeasure)
    if (typeof cfg.sizeMeasure === 'string')
      setSizeMeasure(cfg.sizeMeasure as GraphMeasure | 'none')
    if (typeof cfg.includeAuthors === 'boolean') setIncludeAuthors(cfg.includeAuthors)
  }, [mapMeta.data])

  async function saveAsMap() {
    if (!displayed) return
    const name = window.prompt('Name this map:')
    if (!name || !name.trim()) return
    const workIds = displayed.nodes
      .filter((n) => n.type === 'paper')
      .map((n) => n.id)
    setSavingMap(true)
    setNotice(null)
    setExpandError(null)
    try {
      await api.post<MapDetailView>('/maps', {
        name: name.trim(),
        layout_config: {
          layout,
          xMeasure,
          yMeasure,
          sizeMeasure,
          includeAuthors,
          mode,
          workId: workId ?? null,
        },
        work_ids: workIds,
      })
      setNotice(`Saved map “${name.trim()}” with ${workIds.length} paper(s).`)
    } catch (e) {
      setExpandError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setSavingMap(false)
    }
  }

  function onSelectNode(node: GraphNode) {
    setSelected(node)
    setNotice(null)
    setExpandError(null)
  }

  function clearRobokop() {
    setRobokopGraph(null)
    setNotice(null)
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

  async function expandClaimRobokop() {
    if (!selected) return
    setExpanding(true)
    setExpandError(null)
    setNotice(null)
    try {
      const result = await api.post<ClaimExpansion>(
        `/graph/claims/${selected.id}/expand-robokop`,
      )
      setRobokopGraph(result.graph)
      setNotice(
        result.resolved_terms === 0
          ? 'No entities on this claim could be grounded in ROBOKOP.'
          : `Grounded ${result.resolved_terms} entity(ies) with ` +
              `${result.corroborating_edges} knowledge-graph edge(s).`,
      )
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
      {mapId && (
        <p className="margin-top-4 margin-bottom-0">
          <Link to="/maps">← Saved maps</Link>
        </p>
      )}
      <PageHeading>
        {mapId
          ? mapMeta.data
            ? `Map: ${mapMeta.data.name}`
            : 'Saved map'
          : centered
            ? 'Paper neighborhood'
            : 'Explore the network'}
      </PageHeading>
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

      {/* Layout & measure controls (paper network only). */}
      {measureable && (
        <div className="display-flex flex-wrap flex-align-end margin-bottom-2">
          <div className="margin-right-3">
            <label className="usa-label margin-top-0 font-body-3xs" htmlFor="layout">
              Layout
            </label>
            <select
              id="layout"
              className="usa-select width-auto"
              value={layout}
              onChange={(e) => setLayout(e.target.value as LayoutMode)}
            >
              <option value="force">Force-directed</option>
              <option value="axis">Map by measure (axes)</option>
            </select>
          </div>

          {layout === 'axis' && (
            <>
              <div className="margin-right-3">
                <label className="usa-label margin-top-0 font-body-3xs" htmlFor="x-measure">
                  X axis
                </label>
                <select
                  id="x-measure"
                  className="usa-select width-auto"
                  value={xMeasure}
                  onChange={(e) => setXMeasure(e.target.value as GraphMeasure)}
                >
                  {MEASURES.map((m) => (
                    <option key={m} value={m}>
                      {MEASURE_LABELS[m]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="margin-right-3">
                <label className="usa-label margin-top-0 font-body-3xs" htmlFor="y-measure">
                  Y axis
                </label>
                <select
                  id="y-measure"
                  className="usa-select width-auto"
                  value={yMeasure}
                  onChange={(e) => setYMeasure(e.target.value as GraphMeasure)}
                >
                  {MEASURES.map((m) => (
                    <option key={m} value={m}>
                      {MEASURE_LABELS[m]}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}

          <div>
            <label className="usa-label margin-top-0 font-body-3xs" htmlFor="size-measure">
              Node size
            </label>
            <select
              id="size-measure"
              className="usa-select width-auto"
              value={sizeMeasure}
              onChange={(e) => setSizeMeasure(e.target.value as GraphMeasure | 'none')}
            >
              <option value="none">Uniform</option>
              {MEASURES.map((m) => (
                <option key={m} value={m}>
                  {MEASURE_LABELS[m]}
                </option>
              ))}
            </select>
          </div>

          {status === 'authenticated' && displayed && (
            <div className="margin-left-3">
              <button
                type="button"
                className="usa-button usa-button--outline"
                onClick={saveAsMap}
                disabled={savingMap}
              >
                {savingMap ? 'Saving…' : 'Save as map'}
              </button>
            </div>
          )}
        </div>
      )}

      {notice && (
        <div className="usa-alert usa-alert--info usa-alert--slim margin-y-2" role="status">
          <div className="usa-alert__body">
            <p className="usa-alert__text">{notice}</p>
          </div>
        </div>
      )}

      {robokopGraph && (
        <div className="usa-alert usa-alert--warning usa-alert--slim margin-y-2">
          <div className="usa-alert__body">
            <p className="usa-alert__text">
              Showing ROBOKOP knowledge-graph context (corroborating background
              knowledge, not an extracted assertion).{' '}
              <button
                type="button"
                className="usa-button usa-button--unstyled"
                onClick={clearRobokop}
              >
                Back to the network
              </button>
            </p>
          </div>
        </div>
      )}

      {graph.loading && <Loading label="Building graph…" />}
      {graph.error && <ErrorAlert message={graph.error} />}
      {displayed && (
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-8">
            <NetworkGraph
              view={displayed}
              selectedId={selected?.id}
              onSelectNode={onSelectNode}
              layout={effectiveLayout}
              xMeasure={xMeasure}
              yMeasure={yMeasure}
              sizeMeasure={sizeMeasure}
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
                      <ul className="usa-list usa-list--unstyled">
                        <li>
                          <Link to={`/claims/${selected.id}`}>Open claim</Link>
                        </li>
                        <li className="margin-top-1">
                          {status === 'authenticated' ? (
                            <button
                              type="button"
                              className="usa-button usa-button--outline"
                              onClick={expandClaimRobokop}
                              disabled={expanding}
                            >
                              {expanding ? 'Exploring…' : 'Explore in ROBOKOP'}
                            </button>
                          ) : (
                            <span className="font-body-3xs text-base">
                              <Link to="/login">Sign in</Link> to explore this claim in
                              ROBOKOP.
                            </span>
                          )}
                        </li>
                      </ul>
                    )}
                    {selected.type === 'entity' && selected.id.includes(':') && (
                      <p className="font-body-3xs text-base">
                        Knowledge-graph entity ({selected.id}).
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
