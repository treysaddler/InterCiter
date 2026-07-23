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
import { scaleLinear, scaleSqrt } from 'd3-scale'
import { zoom } from 'd3-zoom'
import { drag } from 'd3-drag'

import type { GraphView, GraphNode } from '../api/types'

/**
 * Reusable network-graph renderer for the exploration views (papers, authors,
 * citations, and later ROBOKOP claims). The same node/edge envelope drives every
 * mode — node color/shape keys off `type`.
 *
 * Rendered with a custom D3 (SVG) renderer. Two layout modes:
 *  - `force` (default): a `d3-force` spring layout — good for topology.
 *  - `axis`: papers positioned on quantitative axes (e.g. x = year, y = citation
 *    count) via `d3-scale`, the Litmaps-style "map papers by a measure" view.
 * Nodes can additionally be sized by a measure. SVG keeps the DOM inspectable and
 * performs well at the current node caps (≤250 per neighborhood).
 *
 * Accessibility (Section 508 / docs/ui-design.md): the SVG canvas is not perceivable
 * to assistive tech, so an equivalent tabular view of the same nodes and edges is
 * always rendered alongside it. Node labels there are buttons, giving keyboard users
 * the same "select a node" affordance the SVG gives pointer users. The SVG is marked
 * `aria-hidden` so it is not double-announced. Whichever measures drive the layout or
 * node size are surfaced as extra columns in that table so the two stay in sync.
 */

/** Quantitative measures a client can map/size paper nodes by (from `node.data`). */
export type GraphMeasure = 'year' | 'cited_by_count' | 'references_count'
export type LayoutMode = 'force' | 'axis'

export const MEASURE_LABELS: Record<GraphMeasure, string> = {
  year: 'Year',
  cited_by_count: 'Cited by',
  references_count: 'References',
}

export interface NetworkGraphProps {
  view: GraphView
  selectedId?: string | null
  onSelectNode?: (node: GraphNode) => void
  height?: number
  /** `force` (default) or quantitative `axis` layout. */
  layout?: LayoutMode
  /** Axis measures (only used when `layout === 'axis'`). */
  xMeasure?: GraphMeasure
  yMeasure?: GraphMeasure
  /** Size paper nodes by this measure; omit/`none` for uniform size. */
  sizeMeasure?: GraphMeasure | 'none'
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
// Plot margins for the axis layout (room for tick labels + axis titles).
const AXIS_PAD = { top: 16, right: 20, bottom: 40, left: 52 }

function colorFor(type: string): string {
  return TYPE_COLOR[type] ?? '#71767a'
}

function truncate(label: string, max = 22): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

/** Finite numeric measure from a node's `data`, else null (missing/non-numeric). */
function measureValue(node: GraphNode, measure: GraphMeasure): number | null {
  const raw = node.data?.[measure]
  const num = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(num) ? num : null
}

function extent(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1]
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (lo === hi) {
    lo -= 1
    hi += 1
  }
  return [lo, hi]
}

// Simulation-augmented mirrors of the API node/edge shapes. d3-force mutates
// these with x/y/vx/vy during layout, so they must be its own local objects.
interface SimNode extends SimulationNodeDatum {
  id: string
  label: string
  type: string
  xVal: number | null
  yVal: number | null
  sizeVal: number | null
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string
  type: string
}

// Draw the per-type node glyph (matches the legend). Cheap inline SVG rather than
// pulling in d3-shape/symbols for four fixed shapes. `radius` sizes the paper circle.
function appendShape(
  g: Selection<SVGGElement, SimNode, null, undefined>,
  type: string,
  radius: number,
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
    base.attr('r', radius) // paper: circle (sizable by measure)
  }
}

export default function NetworkGraph({
  view,
  selectedId,
  onSelectNode,
  height = 480,
  layout = 'force',
  xMeasure = 'year',
  yMeasure = 'cited_by_count',
  sizeMeasure = 'none',
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
        xVal: measureValue(n, xMeasure),
        yVal: measureValue(n, yMeasure),
        sizeVal: sizeMeasure === 'none' ? null : measureValue(n, sizeMeasure),
      }))
      const nodeIds = new Set(nodes.map((n) => n.id))
      const simById = new Map(nodes.map((n) => [n.id, n]))
      const links: SimLink[] = view.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type }))

      // Size paper nodes by a measure (area-proportional), else uniform.
      const sizeValues = nodes
        .map((n) => n.sizeVal)
        .filter((v): v is number => v != null)
      const sizeScale = scaleSqrt()
        .domain(extent(sizeValues))
        .range([6, 20])
      const radiusFor = (d: SimNode): number =>
        d.sizeVal != null ? sizeScale(d.sizeVal) : NODE_RADIUS

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
        appendShape(select<SVGGElement, SimNode>(this), d.type, radiusFor(d))
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

      if (layout === 'axis') {
        // Map papers onto quantitative axes (Litmaps-style year × citations). Static
        // positions from d3-scale — no simulation to fight the fixed coordinates.
        const xScale = scaleLinear()
          .domain(extent(nodes.map((n) => n.xVal).filter((v): v is number => v != null)))
          .range([AXIS_PAD.left, width - AXIS_PAD.right])
          .nice()
        const yScale = scaleLinear()
          .domain(extent(nodes.map((n) => n.yVal).filter((v): v is number => v != null)))
          .range([height - AXIS_PAD.bottom, AXIS_PAD.top])
          .nice()

        const posX = (d: SimNode): number =>
          d.xVal != null ? xScale(d.xVal) : AXIS_PAD.left
        const posY = (d: SimNode): number =>
          d.yVal != null ? yScale(d.yVal) : height - AXIS_PAD.bottom

        // Gridlines + tick labels behind the nodes.
        const axisG = zoomLayer.insert('g', ':first-child').attr('font-size', 9).attr('fill', '#71767a')
        axisG
          .append('g')
          .selectAll('line')
          .data(xScale.ticks(6))
          .join('line')
          .attr('x1', (t) => xScale(t))
          .attr('x2', (t) => xScale(t))
          .attr('y1', AXIS_PAD.top)
          .attr('y2', height - AXIS_PAD.bottom)
          .attr('stroke', '#edeff0')
        axisG
          .append('g')
          .selectAll('text')
          .data(xScale.ticks(6))
          .join('text')
          .attr('x', (t) => xScale(t))
          .attr('y', height - AXIS_PAD.bottom + 14)
          .attr('text-anchor', 'middle')
          .text((t) => String(t))
        axisG
          .append('g')
          .selectAll('line')
          .data(yScale.ticks(6))
          .join('line')
          .attr('y1', (t) => yScale(t))
          .attr('y2', (t) => yScale(t))
          .attr('x1', AXIS_PAD.left)
          .attr('x2', width - AXIS_PAD.right)
          .attr('stroke', '#edeff0')
        axisG
          .append('g')
          .selectAll('text')
          .data(yScale.ticks(6))
          .join('text')
          .attr('x', AXIS_PAD.left - 6)
          .attr('y', (t) => yScale(t) + 3)
          .attr('text-anchor', 'end')
          .text((t) => String(t))
        // Axis titles.
        axisG
          .append('text')
          .attr('x', (AXIS_PAD.left + width - AXIS_PAD.right) / 2)
          .attr('y', height - 6)
          .attr('text-anchor', 'middle')
          .attr('font-weight', 'bold')
          .text(MEASURE_LABELS[xMeasure])
        axisG
          .append('text')
          .attr('transform', `translate(12,${(AXIS_PAD.top + height - AXIS_PAD.bottom) / 2}) rotate(-90)`)
          .attr('text-anchor', 'middle')
          .attr('font-weight', 'bold')
          .text(MEASURE_LABELS[yMeasure])

        nodes.forEach((n) => {
          n.x = posX(n)
          n.y = posY(n)
        })
        node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
        link
          .attr('x1', (d) => simById.get(d.source as string)?.x ?? 0)
          .attr('y1', (d) => simById.get(d.source as string)?.y ?? 0)
          .attr('x2', (d) => simById.get(d.target as string)?.x ?? 0)
          .attr('y2', (d) => simById.get(d.target as string)?.y ?? 0)
      } else {
        // Let users pin/reposition nodes (only meaningful in the free force layout).
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
      }
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
  }, [view, nodesById, onSelectNode, height, layout, xMeasure, yMeasure, sizeMeasure])

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

  // Measures currently driving the view — surfaced as table columns so the accessible
  // representation stays in sync with the (aria-hidden) axis/size encoding.
  const activeMeasures: GraphMeasure[] = Array.from(
    new Set<GraphMeasure>([
      ...(layout === 'axis' ? [xMeasure, yMeasure] : []),
      ...(sizeMeasure !== 'none' ? [sizeMeasure] : []),
    ]),
  )

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
              {activeMeasures.map((m) => (
                <th scope="col" key={m}>
                  {MEASURE_LABELS[m]}
                </th>
              ))}
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
                {activeMeasures.map((m) => {
                  const v = measureValue(n, m)
                  return <td key={m}>{v == null ? '—' : v}</td>
                })}
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
