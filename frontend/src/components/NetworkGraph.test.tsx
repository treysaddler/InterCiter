import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import NetworkGraph from './NetworkGraph'
import type { GraphView } from '../api/types'

// Cytoscape renders to a Canvas, which jsdom does not implement. Mock it so the
// component's accessible fallback (the part we assert on) renders without a canvas.
vi.mock('cytoscape', () => ({
  default: () => ({
    on: vi.fn(),
    nodes: () => ({ removeClass: vi.fn() }),
    getElementById: () => ({ addClass: vi.fn() }),
    destroy: vi.fn(),
  }),
}))

const view: GraphView = {
  nodes: [
    { id: 'work_a', type: 'paper', label: 'Paper A', data: {} },
    { id: 'work_b', type: 'paper', label: 'Paper B', data: {} },
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
