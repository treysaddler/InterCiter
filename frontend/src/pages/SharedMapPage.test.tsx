import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import SharedMapPage from './SharedMapPage'
import { api } from '../api/client'

// Stub the heavy d3 renderer; this test is about the shared-map read-only wiring,
// not the SVG. The stub exposes a select button per node to drive node selection.
vi.mock('../components/NetworkGraph', () => ({
  default: ({
    view,
    onSelectNode,
  }: {
    view: { nodes: { id: string }[] }
    onSelectNode?: (n: { id: string }) => void
  }) => (
    <div data-testid="network-graph">
      {view.nodes.map((n) => (
        <button key={n.id} type="button" onClick={() => onSelectNode?.(n)}>
          select-{n.id}
        </button>
      ))}
    </div>
  ),
}))

vi.mock('../api/client', () => {
  class ApiError extends Error {}
  return { api: { get: vi.fn() }, ApiError }
})

const mockedGet = vi.mocked(api.get)

const SHARED = {
  map_id: 'map_1',
  name: 'T2D core',
  description: 'glycemic control',
  layout_config: { layout: 'axis', xMeasure: 'year', yMeasure: 'cited_by_count' },
  member_count: 2,
  members: [
    {
      map_membership_id: 'mmem_1',
      work_id: 'work_a',
      title: 'A',
      doi: null,
      pmid: null,
      year: 2020,
      note: 'key trial',
      position: null,
      added_at: '2026-01-01T00:00:00Z',
    },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

const GRAPH = {
  nodes: [{ id: 'work_a', type: 'paper', label: 'A', data: {} }],
  edges: [],
  center_id: null,
  truncated: false,
}

function renderAt(token: string) {
  return render(
    <MemoryRouter initialEntries={[`/shared/${token}`]}>
      <Routes>
        <Route path="/shared/:token" element={<SharedMapPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

it('renders a shared map read-only by token (name, notice, network)', async () => {
  mockedGet.mockImplementation((url: string) =>
    Promise.resolve(url.endsWith('/graph') ? GRAPH : SHARED),
  )
  renderAt('tok123')

  expect(await screen.findByRole('heading', { name: 'T2D core' })).toBeInTheDocument()
  expect(screen.getByText(/read-only citation map/i)).toBeInTheDocument()
  expect(mockedGet).toHaveBeenCalledWith('/shared-maps/tok123')
  expect(mockedGet).toHaveBeenCalledWith('/shared-maps/tok123/graph')
  expect(screen.getByTestId('network-graph')).toBeInTheDocument()
})

it('shows a member note when its node is selected, with no write actions', async () => {
  mockedGet.mockImplementation((url: string) =>
    Promise.resolve(url.endsWith('/graph') ? GRAPH : SHARED),
  )
  renderAt('tok123')

  await screen.findByRole('heading', { name: 'T2D core' })
  await userEvent.click(screen.getByRole('button', { name: 'select-work_a' }))
  expect(screen.getByText(/key trial/)).toBeInTheDocument()
  // Read-only: no share/save/expand controls are exposed.
  expect(screen.queryByRole('button', { name: /share|save|expand/i })).toBeNull()
})

it('surfaces an error for a revoked or unknown token', async () => {
  mockedGet.mockRejectedValue(new Error('shared map not found'))
  renderAt('gone')
  expect(await screen.findByText(/shared map not found/i)).toBeInTheDocument()
})
