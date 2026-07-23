import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import MapsPage from './MapsPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), del: vi.fn(), post: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)
const mockedDel = vi.mocked(api.del)
const mockedPost = vi.mocked(api.post)

const MAPS = [
  {
    map_id: 'map_1',
    owner_id: 'user_1',
    name: 'T2D core',
    description: 'glycemic control',
    layout_config: { layout: 'axis' },
    member_count: 3,
    share_token: null,
    is_watched: false,
    watch_last_checked_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

it('lists saved maps with a link into the explorer', async () => {
  mockedGet.mockResolvedValue(MAPS)
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  const link = await screen.findByRole('link', { name: 'T2D core' })
  expect(link).toHaveAttribute('href', '/graph?map=map_1')
  expect(screen.getByText('3')).toBeInTheDocument()
})

it('deletes a map after confirmation and reloads', async () => {
  mockedGet.mockResolvedValue(MAPS)
  mockedDel.mockResolvedValue(undefined)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: 'T2D core' })
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(mockedDel).toHaveBeenCalledWith('/maps/map_1'))
})

it('shows an empty state when there are no maps', async () => {
  mockedGet.mockResolvedValue([])
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText(/no saved maps yet/i)).toBeInTheDocument()
})

it('mints a read-only share link and copies it to the clipboard', async () => {
  mockedGet.mockResolvedValue(MAPS)
  mockedPost.mockResolvedValue({ map_id: 'map_1', share_token: 'tok123' })
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: 'T2D core' })
  fireEvent.click(screen.getByRole('button', { name: 'Share' }))
  await waitFor(() =>
    expect(mockedPost).toHaveBeenCalledWith('/maps/map_1/share'),
  )
  await waitFor(() =>
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/shared/tok123')),
  )
  // The list reloads so the newly-minted token surfaces the Copy link / Revoke pair.
  expect(mockedGet).toHaveBeenCalledTimes(2)
})

it('revokes a share link after confirmation', async () => {
  mockedGet.mockResolvedValue([{ ...MAPS[0], share_token: 'tok123' }])
  mockedDel.mockResolvedValue(undefined)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: 'T2D core' })
  fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))
  await waitFor(() =>
    expect(mockedDel).toHaveBeenCalledWith('/maps/map_1/share'),
  )
})

it('watches a map and then runs a monitor check', async () => {
  mockedGet.mockResolvedValue(MAPS)
  mockedPost.mockResolvedValue({ ...MAPS[0], is_watched: true })
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: 'T2D core' })
  fireEvent.click(screen.getByRole('button', { name: 'Watch' }))
  await waitFor(() =>
    expect(mockedPost).toHaveBeenCalledWith('/maps/map_1/watch', { watch: true }),
  )
})

it('runs a monitor check for a watched map and surfaces the result', async () => {
  mockedGet.mockResolvedValue([{ ...MAPS[0], is_watched: true }])
  mockedPost.mockResolvedValue({ created_count: 2, alerts: [] })
  render(
    <MemoryRouter>
      <MapsPage />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: 'T2D core' })
  fireEvent.click(screen.getByRole('button', { name: 'Check now' }))
  await waitFor(() =>
    expect(mockedPost).toHaveBeenCalledWith('/maps/map_1/monitor'),
  )
  expect(await screen.findByText(/2 newly connected paper/i)).toBeInTheDocument()
})
