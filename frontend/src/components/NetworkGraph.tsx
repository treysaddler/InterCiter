import { useEffect, useMemo, useRef } from 'react'
import { select, type Selection } from 'd3-selection'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import { zoom } from 'd3-zoom'
import { drag } from 'd3-drag'

import type { GraphView, GraphNode } from '../api/types'

/**
 * Reusable network-graph renderer for the exploration views (papers, authors,
 * citations, and later ROBOKOP claims). The same node/edge envelope drives every
 * mode — node color/shape keys off `type`.
 *
 * Rendered with a custom D3 (SVG) force layout. SVG keeps the DOM inspectable and
 * performs well at the current node caps (≤250 per neighborhood); modular d3
 * (selection/force/zoom/drag) is a much smaller bundle than a full graph library.
 *
 * Accessibility (Section 508 / docs/ui-design.md): the SVG canvas is not perceivable
 * to assistive tech, so an equivalent tabular view of the same nodes and edges is
 * always rendered alongside it. Node labels there are buttons, giving keyboard users
 * the same "select a node" affordance the SVG gives pointer users. The SVG is marked
 * `aria-hidden` so it is not double-announced.
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
  entity: '#8168b3', // violet (ROBOKOP knowledge-graph entities)
}

const SELECTED_COLOR = '#fa9441'
const NODE_RADIUS = 9

function colorFor(type: string): string {
  return TYPE_COLOR[type] ?? '#71767a'
}

function truncate(label: string, max = 22): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

// Simulation-augmented mirrors of the API node/edge shapes. d3-force mutates
// these with x/y/vx/vy during layout, so they must be its own local objects.
interface SimNode extends SimulationNodeDatum {
  id: string
  label: string
  type: string
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string
  type: string
}

// Draw the per-type node glyph (matches the legend). Cheap inline SVG rather than
// pulling in d3-shape/symbols for four fixed shapes.
function appendShape(
  g: Selection<SVGGElement, SimNode, null, undefined>,
  type: string,
): void {
  const color = colorFor(type)
  const r = NODE_RADIUS
  const shapeTag =
    type === 'author' || type === 'entity'
      ? 'polygon'
      : type === 'claim'
        ? 'rect'
        : 'circle'
  const base = g
    .append(shapeTag)
    .attr('class', 'ic-node-shape')
    .attr('fill', color)
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 1.5)
  if (type === 'author') {
    base.attr('points', `0,${-r - 2} ${r + 2},0 0,${r + 2} ${-r - 2},0`) // diamond
  } else if (type === 'claim') {
    base
      .attr('x', -r - 1)
      .attr('y', -r + 2)
      .attr('width', (r + 1) * 2)
      .attr('height', (r - 2) * 2)
      .attr('rx', 3)
  } else if (type === 'entity') {
    const h = r + 1
    base.attr(
      'points',
      `${-h},0 ${-h / 2},${-h} ${h / 2},${-h} ${h},0 ${h / 2},${h} ${-h / 2},${h}`,
    ) // hexagon
  } else {
    base.attr('r', r) // paper: circle
  }
}

export default function NetworkGraph({
  view,
  selectedId,
  onSelectNode,
  height = 480,
}: NetworkGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null)
  const nodeSelRef = useRef<Selection<SVGGElement, SimNode, SVGGElement, unknown> | null>(null)
  const nodesById = useMemo(
    () => new Map(view.nodes.map((n) => [n.id, n])),
    [view.nodes],
  )

  // (Re)build the graph whenever the data changes.
  useEffect(() => {
    const container = containerRef.current
    const svgEl = svgRef.current
    if (!container || !svgEl) return
    let sim: Simulation<SimNode, SimLink> | null = null
    try {
      const width = container.clientWidth || 600
      const nodes: SimNode[] = view.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        type: n.type,
      }))
      const nodeIds = new Set(nodes.map((n) => n.id))
      const links: SimLink[] = view.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type }))

      const svg = select(svgEl)
      svg.selectAll('*').remove()

      // Arrowhead for directed (citation) edges.
      svg
        .append('defs')
        .append('marker')
        .attr('id', 'ic-arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', NODE_RADIUS + 8)
        .attr('refY', 0)
        .attr('markerWidth', 5)
        .attr('markerHeight', 5)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#a9aeb1')

      const zoomLayer = svg.append('g')

      const link = zoomLayer
        .append('g')
        .selectAll<SVGLineElement, SimLink>('line')
        .data(links)
        .join('line')
        .attr('stroke', (d) => (d.type === 'authored' ? '#00a91c' : '#a9aeb1'))
        .attr('stroke-width', (d) => (d.type === 'authored' ? 1 : 1.5))
        .attr('marker-end', (d) => (d.type === 'authored' ? null : 'url(#ic-arrow)'))

      const node = zoomLayer
        .append('g')
        .selectAll<SVGGElement, SimNode>('g')
        .data(nodes)
        .join('g')
        .attr('cursor', 'pointer')
        .on('click', (_event, d) => {
          const gn = nodesById.get(d.id)
          if (gn && onSelectNode) onSelectNode(gn)
        })

      node.each(function (d) {
        appendShape(select<SVGGElement, SimNode>(this), d.type)
      })

      node
        .append('text')
        .text((d) => truncate(d.label))
        .attr('text-anchor', 'middle')
        .attr('y', NODE_RADIUS + 12)
        .attr('font-size', 10)
        .attr('fill', '#1b1b1b')
        .attr('pointer-events', 'none')

      nodeSelRef.current = node

      // Pan/zoom the whole layout.
      svg.call(
        zoom<SVGSVGElement, unknown>()
          .scaleExtent([0.2, 4])
          .on('zoom', (event) => zoomLayer.attr('transform', event.transform)),
      )

      // Let users pin/reposition nodes.
      node.call(
        drag<SVGGElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) sim?.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) sim?.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )

      sim = forceSimulation<SimNode>(nodes)
        .force(
          'link',
          forceLink<SimNode, SimLink>(links)
            .id((d) => d.id)
            .distance(70),
        )
        .force('charge', forceManyBody().strength(-180))
        .force('center', forceCenter(width / 2, height / 2))
        .force('collide', forceCollide(NODE_RADIUS + 12))
        .on('tick', () => {
          link
            .attr('x1', (d) => (d.source as SimNode).x ?? 0)
            .attr('y1', (d) => (d.source as SimNode).y ?? 0)
            .attr('x2', (d) => (d.target as SimNode).x ?? 0)
            .attr('y2', (d) => (d.target as SimNode).y ?? 0)
          node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
        })
      simRef.current = sim
    } catch {
      // SVG/layout is unavailable (e.g. jsdom in tests) — the accessible table
      // below still conveys the full graph. Fail soft rather than crash the page.
      simRef.current = null
      nodeSelRef.current = null
    }
    return () => {
      sim?.stop()
      simRef.current = null
      nodeSelRef.current = null
    }
  }, [view, nodesById, onSelectNode, height])

  // Reflect the current selection onto the SVG without a full rebuild.
  useEffect(() => {
    const node = nodeSelRef.current
    if (!node) return
    try {
      node
        .select('.ic-node-shape')
        .attr('stroke', (d) => ((d as SimNode).id === selectedId ? SELECTED_COLOR : '#ffffff'))
        .attr('stroke-width', (d) => ((d as SimNode).id === selectedId ? 3 : 1.5))
    } catch {
      // no-op: selection styling is decorative; the a11y table is authoritative.
    }
  }, [selectedId, view])

  const types = Array.from(new Set(view.nodes.map((n) => n.type)))

  return (
    <div>
      <div
        ref={containerRef}
        style={{
          height,
          border: '1px solid #dfe1e2',
          borderRadius: 4,
          background: '#fbfcfd',
          overflow: 'hidden',
        }}
      >
        <svg
          ref={svgRef}
          aria-hidden="true"
          width="100%"
          height={height}
          style={{ display: 'block' }}
        />
      </div>
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
