import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import type { Core, ElementDefinition, StylesheetStyle } from 'cytoscape'

import type { GraphView, GraphNode } from '../api/types'

/**
 * Reusable network-graph renderer for the exploration views (papers, authors,
 * citations, and later ROBOKOP claims). The same node/edge envelope drives every
 * mode — node color/shape keys off `type`.
 *
 * Accessibility (Section 508 / docs/ui-design.md): a Canvas graph is not perceivable
 * to assistive tech, so an equivalent tabular view of the same nodes and edges is
 * always rendered alongside it. Node labels there are buttons, giving keyboard users
 * the same "select a node" affordance the canvas gives pointer users. The canvas is
 * marked `aria-hidden` so it is not double-announced.
 */

export interface NetworkGraphProps {
  view: GraphView
  selectedId?: string | null
  onSelectNode?: (node: GraphNode) => void
  height?: number
}

// USWDS-adjacent palette; kept in one place so legend + graph agree.
const TYPE_COLOR: Record<string, string> = {
  paper: '#005ea2', // primary blue
  author: '#00a91c', // green
  claim: '#c05600', // orange
}

function colorFor(type: string): string {
  return TYPE_COLOR[type] ?? '#71767a'
}

function stylesheet(): StylesheetStyle[] {
  return [
    {
      selector: 'node',
      style: {
        label: 'data(label)',
        'background-color': '#71767a',
        color: '#1b1b1b',
        'font-size': 10,
        'text-wrap': 'ellipsis',
        'text-max-width': '120px',
        'text-valign': 'bottom',
        'text-margin-y': 3,
        width: 18,
        height: 18,
      },
    },
    {
      selector: 'node.type-paper',
      style: { 'background-color': TYPE_COLOR.paper, shape: 'ellipse' },
    },
    {
      selector: 'node.type-author',
      style: { 'background-color': TYPE_COLOR.author, shape: 'diamond' },
    },
    {
      selector: 'node.type-claim',
      style: { 'background-color': TYPE_COLOR.claim, shape: 'round-rectangle' },
    },
    {
      selector: 'node.selected',
      style: { 'border-width': 3, 'border-color': '#fa9441', width: 26, height: 26 },
    },
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': '#a9aeb1',
        'target-arrow-color': '#a9aeb1',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'arrow-scale': 0.8,
      },
    },
    {
      selector: 'edge[type = "authored"]',
      style: { 'line-color': '#00a91c', 'target-arrow-shape': 'none', width: 1 },
    },
  ]
}

function toElements(view: GraphView): ElementDefinition[] {
  const nodeIds = new Set(view.nodes.map((n) => n.id))
  const nodes: ElementDefinition[] = view.nodes.map((n) => ({
    data: { id: n.id, label: n.label, type: n.type },
    classes: `type-${n.type}`,
  }))
  const edges: ElementDefinition[] = view.edges
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e) => ({
      data: { id: e.id, source: e.source, target: e.target, type: e.type },
    }))
  return [...nodes, ...edges]
}

export default function NetworkGraph({
  view,
  selectedId,
  onSelectNode,
  height = 480,
}: NetworkGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)
  const nodesById = useMemo(
    () => new Map(view.nodes.map((n) => [n.id, n])),
    [view.nodes],
  )

  // (Re)build the graph whenever the data changes.
  useEffect(() => {
    if (!containerRef.current) return
    let cy: Core | null = null
    try {
      cy = cytoscape({
        container: containerRef.current,
        elements: toElements(view),
        style: stylesheet(),
        layout: { name: 'cose', animate: false, padding: 20 },
        wheelSensitivity: 0.2,
      })
      cy.on('tap', 'node', (evt) => {
        const node = nodesById.get(evt.target.id())
        if (node && onSelectNode) onSelectNode(node)
      })
      cyRef.current = cy
    } catch {
      // Canvas is unavailable (e.g. jsdom in tests) — the accessible table below
      // still conveys the full graph. Fail soft rather than crash the page.
      cyRef.current = null
    }
    return () => {
      cy?.destroy()
      cyRef.current = null
    }
  }, [view, nodesById, onSelectNode])

  // Reflect the current selection onto the canvas without a full rebuild.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().removeClass('selected')
    if (selectedId) cy.getElementById(selectedId).addClass('selected')
  }, [selectedId, view])

  const types = Array.from(new Set(view.nodes.map((n) => n.type)))

  return (
    <div>
      <div
        ref={containerRef}
        aria-hidden="true"
        style={{
          height,
          border: '1px solid #dfe1e2',
          borderRadius: 4,
          background: '#fbfcfd',
        }}
      />
      {types.length > 0 && (
        <ul
          className="usa-list usa-list--unstyled display-flex flex-wrap margin-top-1"
          aria-label="Node types shown"
        >
          {types.map((t) => (
            <li key={t} className="margin-right-2 font-body-3xs">
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: t === 'author' ? 0 : 6,
                  background: colorFor(t),
                  marginRight: 4,
                }}
              />
              {t}
            </li>
          ))}
        </ul>
      )}

      <details className="margin-top-2">
        <summary>Graph data (accessible view)</summary>
        <p className="font-body-3xs text-base">
          {view.nodes.length} nodes, {view.edges.length} edges
          {view.truncated ? ' (view truncated — narrow the query to see more).' : '.'}
        </p>
        <h3 className="font-body-xs margin-bottom-1">Nodes</h3>
        <table className="usa-table usa-table--compact usa-table--borderless width-full">
          <caption className="usa-sr-only">Graph nodes</caption>
          <thead>
            <tr>
              <th scope="col">Type</th>
              <th scope="col">Label</th>
            </tr>
          </thead>
          <tbody>
            {view.nodes.map((n) => (
              <tr key={n.id}>
                <td>{n.type}</td>
                <td>
                  {onSelectNode ? (
                    <button
                      type="button"
                      className="usa-button usa-button--unstyled"
                      onClick={() => onSelectNode(n)}
                    >
                      {n.label}
                    </button>
                  ) : (
                    n.label
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3 className="font-body-xs margin-bottom-1">Edges</h3>
        <table className="usa-table usa-table--compact usa-table--borderless width-full">
          <caption className="usa-sr-only">Graph edges</caption>
          <thead>
            <tr>
              <th scope="col">Relation</th>
              <th scope="col">From</th>
              <th scope="col">To</th>
            </tr>
          </thead>
          <tbody>
            {view.edges.map((e) => (
              <tr key={e.id}>
                <td>{e.label ?? e.type}</td>
                <td>{nodesById.get(e.source)?.label ?? e.source}</td>
                <td>{nodesById.get(e.target)?.label ?? e.target}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
