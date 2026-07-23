import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { GraphNode, GraphView, SharedMapView } from '../api/types'
import NetworkGraph, {
  type GraphMeasure,
  type LayoutMode,
} from '../components/NetworkGraph'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Public, read-only shared-map viewer (litmaps-parity WP-L4). Reachable at
 * `/shared/:token` WITHOUT authentication — the token is the sole capability. It
 * renders the shared map's citation network and per-node notes, but exposes no
 * write actions and never surfaces the owner's identity (the API projection omits
 * it). A revoked or unknown token resolves to an error.
 */
export default function SharedMapPage() {
  const { token } = useParams()
  const [selected, setSelected] = useState<GraphNode | null>(null)

  const meta = useApi<SharedMapView>(
    () => api.get<SharedMapView>(`/shared-maps/${token}`),
    [token],
  )
  const graph = useApi<GraphView>(
    () => api.get<GraphView>(`/shared-maps/${token}/graph`),
    [token],
  )

  const cfg = meta.data?.layout_config ?? {}
  const layout: LayoutMode = cfg.layout === 'axis' ? 'axis' : 'force'
  const xMeasure = (typeof cfg.xMeasure === 'string' ? cfg.xMeasure : 'year') as GraphMeasure
  const yMeasure = (typeof cfg.yMeasure === 'string'
    ? cfg.yMeasure
    : 'cited_by_count') as GraphMeasure
  const sizeMeasure = (typeof cfg.sizeMeasure === 'string' ? cfg.sizeMeasure : 'none') as
    | GraphMeasure
    | 'none'

  // Per-work annotations from the shared map's members, for the a11y table.
  const noteByWork: Record<string, string> = {}
  for (const m of meta.data?.members ?? []) {
    if (m.note) noteByWork[m.work_id] = m.note
  }

  return (
    <>
      <div className="usa-alert usa-alert--info usa-alert--slim margin-top-4">
        <div className="usa-alert__body">
          <p className="usa-alert__text">
            You are viewing a shared, read-only citation map.
          </p>
        </div>
      </div>

      <PageHeading>{meta.data ? meta.data.name : 'Shared map'}</PageHeading>
      {meta.data?.description && (
        <p className="text-base measure-5">{meta.data.description}</p>
      )}

      {(meta.loading || graph.loading) && <Loading label="Loading shared map…" />}
      {meta.error && <ErrorAlert message={meta.error} />}
      {graph.error && !meta.error && <ErrorAlert message={graph.error} />}

      {graph.data && (
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-8">
            <NetworkGraph
              view={graph.data}
              selectedId={selected?.id}
              onSelectNode={setSelected}
              layout={layout}
              xMeasure={xMeasure}
              yMeasure={yMeasure}
              sizeMeasure={sizeMeasure}
              notes={noteByWork}
            />
          </div>
          <div className="tablet:grid-col-4">
            <aside className="usa-summary-box" aria-label="Selected node">
              <div className="usa-summary-box__body">
                {!selected && (
                  <p className="usa-summary-box__text">
                    Select a node to see details.
                  </p>
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
                        {noteByWork[selected.id] && (
                          <li className="margin-top-1 font-body-3xs">
                            <strong>Note:</strong> {noteByWork[selected.id]}
                          </li>
                        )}
                      </ul>
                    )}
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
