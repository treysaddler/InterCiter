import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { GraphNode, GraphView } from '../api/types'
import { useApi } from '../hooks/useApi'
import NetworkGraph from './NetworkGraph'
import { ErrorAlert, Loading } from './States'

/**
 * The citation network for a focused search result, rendered inline with the results
 * so exploration flows straight out of search (docs/ui-design.md). Given the paper a
 * matched claim belongs to, it shows that paper's citation neighborhood; selecting
 * another paper node re-focuses the network on it, letting a reader walk the context
 * without leaving the search screen.
 *
 * Heavy (Cytoscape) — always mount this behind `React.lazy` so it stays out of the
 * initial bundle.
 */
export default function SearchNetwork({
  workId,
  title,
  onFocusPaper,
}: {
  workId: string
  title?: string | null
  onFocusPaper?: (workId: string) => void
}) {
  const graph = useApi<GraphView>(
    () => api.get<GraphView>(`/graph/papers/${workId}?depth=1&include_authors=false`),
    [workId],
  )

  function onSelectNode(node: GraphNode) {
    // Re-focus the network on another paper; ignore author/claim/entity nodes.
    if (node.type === 'paper' && node.id !== workId) onFocusPaper?.(node.id)
  }

  return (
    <section
      className="margin-bottom-3 padding-2 bg-base-lightest radius-md"
      aria-label="Citation network for the focused result"
    >
      <div className="display-flex flex-align-center flex-justify margin-bottom-1">
        <h3 className="font-heading-sm margin-0">Citation network</h3>
        <Link to={`/graph/papers/${workId}`} className="font-body-3xs">
          Open full network ↗
        </Link>
      </div>
      <p className="font-body-3xs text-base margin-top-0 margin-bottom-1">
        {title ? (
          <>
            Around <span className="text-bold">{title}</span>. Select a paper to
            re-center.
          </>
        ) : (
          'Select a paper to re-center.'
        )}
      </p>

      {graph.loading && <Loading label="Loading network…" />}
      {graph.error && <ErrorAlert message={graph.error} />}
      {graph.data && (
        <NetworkGraph
          view={graph.data}
          selectedId={workId}
          onSelectNode={onSelectNode}
          height={360}
        />
      )}
    </section>
  )
}
