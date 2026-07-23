import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import GraphPage from './GraphPage'
import { api } from '../api/client'

// NetworkGraph is the heavy d3 renderer; stub it (this page test is about the map
// save/load/annotate wiring, not the SVG). The stub exposes a select button per node
// so tests can drive node selection.
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
  MEASURE_LABELS: { year: 'Year', cited_by_count: 'Cited by', references_count: 'References' },
}))

const mockStatus = vi.fn(() => 'authenticated')
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ status: mockStatus() }),
}))

vi.mock('../api/client', () => {
  class ApiError extends Error {}
  return { api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }, ApiError }
})

const mockedGet = vi.mocked(api.get)
const mockedPost = vi.mocked(api.post)
const mockedPatch = vi.mocked(api.patch)

const GRAPH = {
  nodes: [
    { id: 'work_a', type: 'paper', label: 'A', data: {} },
    { id: 'work_b', type: 'paper', label: 'B', data: {} },
  ],
  edges: [],
  center_id: null,
  truncated: false,
}

const MAP_DETAIL = {
  map_id: 'map_1',
  owner_id: 'user_1',
  name: 'T2D core',
  description: null,
  layout_config: { layout: 'axis', xMeasure: 'year', yMeasure: 'cited_by_count' },
  member_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  members: [
    {
      map_membership_id: 'mmem_a',
      work_id: 'work_a',
      title: 'A',
      doi: null,
      pmid: null,
      year: 2020,
      note: null,
      position: null,
      added_at: '2026-01-01T00:00:00Z',
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  mockStatus.mockReturnValue('authenticated')
})

it('saves the current view as a map with its paper node ids', async () => {
  mockedGet.mockResolvedValue(GRAPH)
  mockedPost.mockResolvedValue(MAP_DETAIL)
  vi.spyOn(window, 'prompt').mockReturnValue('My map')

  render(
    <MemoryRouter initialEntries={['/graph']}>
      <GraphPage />
    </MemoryRouter>,
  )

  const saveBtn = await screen.findByRole('button', { name: 'Save as map' })
  await userEvent.click(saveBtn)

  await waitFor(() =>
    expect(mockedPost).toHaveBeenCalledWith(
      '/maps',
      expect.objectContaining({ name: 'My map', work_ids: ['work_a', 'work_b'] }),
    ),
  )
})

it('loads a saved map: renders its graph and hydrates the name', async () => {
  mockedGet.mockImplementation((url: string) => {
    if (url === '/maps/map_1') return Promise.resolve(MAP_DETAIL)
    return Promise.resolve(GRAPH) // /maps/map_1/graph
  })

  render(
    <MemoryRouter initialEntries={['/graph?map=map_1']}>
      <GraphPage />
    </MemoryRouter>,
  )

  expect(await screen.findByText('Map: T2D core')).toBeInTheDocument()
  expect(mockedGet).toHaveBeenCalledWith('/maps/map_1/graph?include_authors=false')
})

it('edits a per-node annotation on a loaded map member via PATCH', async () => {
  mockedGet.mockImplementation((url: string) => {
    if (url === '/maps/map_1') return Promise.resolve(MAP_DETAIL)
    return Promise.resolve(GRAPH) // /maps/map_1/graph
  })
  mockedPatch.mockResolvedValue({})

  render(
    <MemoryRouter initialEntries={['/graph?map=map_1']}>
      <GraphPage />
    </MemoryRouter>,
  )

  // Select the member paper node to reveal the note editor.
  await userEvent.click(await screen.findByRole('button', { name: 'select-work_a' }))
  const editor = await screen.findByLabelText('Note on this paper')
  await userEvent.type(editor, 'key trial')
  await userEvent.click(screen.getByRole('button', { name: 'Save note' }))

  await waitFor(() =>
    expect(mockedPatch).toHaveBeenCalledWith('/maps/map_1/members/work_a', {
      note: 'key trial',
    }),
  )
})
