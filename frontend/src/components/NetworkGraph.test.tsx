import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import NetworkGraph from './NetworkGraph'
import type { GraphView } from '../api/types'

// The SVG renderer uses modular d3 (selection/force/zoom/drag). jsdom has no layout
// engine, so mock the d3 entry points with a self-returning chainable stub. The
// component's accessible fallback (the part we assert on) then renders unaffected.
const chain = (): unknown => {
  const proxy: unknown = new Proxy(function () {}, {
    get: () => () => proxy,
    apply: () => proxy,
  })
  return proxy
}

vi.mock('d3-selection', () => ({ select: () => chain() }))
vi.mock('d3-force', () => ({
  forceSimulation: () => chain(),
  forceLink: () => chain(),
  forceManyBody: () => chain(),
  forceCenter: () => chain(),
  forceCollide: () => chain(),
}))
vi.mock('d3-zoom', () => ({ zoom: () => chain() }))
vi.mock('d3-drag', () => ({ drag: () => chain() }))
vi.mock('d3-scale', () => ({ scaleLinear: () => chain(), scaleSqrt: () => chain() }))

const view: GraphView = {
  nodes: [
    { id: 'work_a', type: 'paper', label: 'Paper A', data: { year: 2020, cited_by_count: 5 } },
    { id: 'work_b', type: 'paper', label: 'Paper B', data: { year: 2018, cited_by_count: 12 } },
    { id: 'author_1', type: 'author', label: 'Jane Doe', data: {} },
  ],
  edges: [
    {
      id: 'cites:work_a->work_b',
      source: 'work_a',
      target: 'work_b',
      type: 'cites',
      label: null,
      data: {},
    },
    {
      id: 'authored:author_1->work_a',
      source: 'author_1',
      target: 'work_a',
      type: 'authored',
      label: null,
      data: {},
    },
  ],
  center_id: null,
  truncated: false,
}

test('renders an accessible table of nodes and edges', () => {
  render(<NetworkGraph view={view} />)
  expect(screen.getByText('3 nodes, 2 edges.')).toBeInTheDocument()
  // Node + edge rows both reference the author label.
  expect(screen.getAllByText('Jane Doe').length).toBeGreaterThan(0)
  // Edge rows resolve endpoint labels.
  expect(screen.getByText('cites')).toBeInTheDocument()
})

test('node labels are buttons that select the node when onSelectNode is given', async () => {
  const onSelectNode = vi.fn()
  render(<NetworkGraph view={view} onSelectNode={onSelectNode} />)
  await userEvent.click(screen.getByRole('button', { name: 'Paper A' }))
  expect(onSelectNode).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'work_a', type: 'paper' }),
  )
})

test('reports truncation in the accessible summary', () => {
  render(<NetworkGraph view={{ ...view, truncated: true }} />)
  expect(screen.getByText(/view truncated/i)).toBeInTheDocument()
})

test('legend lists the node types present', () => {
  render(<NetworkGraph view={view} />)
  const legend = within(screen.getByLabelText('Node types shown'))
  expect(legend.getByText('paper')).toBeInTheDocument()
  expect(legend.getByText('author')).toBeInTheDocument()
})

test('axis layout surfaces the active measures as accessible table columns', () => {
  render(
    <NetworkGraph
      view={view}
      layout="axis"
      xMeasure="year"
      yMeasure="cited_by_count"
    />,
  )
  // Column headers for both axis measures appear in the node table.
  expect(screen.getByRole('columnheader', { name: 'Year' })).toBeInTheDocument()
  expect(screen.getByRole('columnheader', { name: 'Cited by' })).toBeInTheDocument()
  // And the per-node measure values are rendered (a node missing a measure shows —).
  expect(screen.getByText('2020')).toBeInTheDocument()
  expect(screen.getByText('12')).toBeInTheDocument()
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

test('force layout adds no measure columns', () => {
  render(<NetworkGraph view={view} />)
  expect(screen.queryByRole('columnheader', { name: 'Cited by' })).toBeNull()
})

test('shows a Note column with per-node annotations when notes are provided', () => {
  render(<NetworkGraph view={view} notes={{ work_a: 'seminal work' }} />)
  expect(screen.getByRole('columnheader', { name: 'Note' })).toBeInTheDocument()
  expect(screen.getByText('seminal work')).toBeInTheDocument()
})

test('omits the Note column when no notes are provided', () => {
  render(<NetworkGraph view={view} />)
  expect(screen.queryByRole('columnheader', { name: 'Note' })).toBeNull()
})
