import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AlertsPage from './AlertsPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), del: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)
const mockedPost = vi.mocked(api.post)

const SAVED_SEARCHES = [
  {
    saved_search_id: 'ssch_1',
    owner_id: 'user_1',
    name: 'Metformin',
    query: {
      q: 'metformin',
      section: null,
      function: null,
      stance: 'support',
      resolution: null,
      min_year: null,
      max_year: null,
    },
    last_checked_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const ALERTS = [
  {
    alert_id: 'alrt_1',
    source_type: 'collection',
    source_id: 'coll_1',
    alert_type: 'new_support',
    work_id: 'work_1',
    claim_id: null,
    summary: '"Watched": A trial gained 2 new supporting citation(s)',
    is_read: false,
    created_at: '2026-01-02T00:00:00Z',
  },
]

function mockLists(alerts = ALERTS, searches = SAVED_SEARCHES) {
  mockedGet.mockImplementation((url: string) => {
    if (url.startsWith('/saved-searches')) return Promise.resolve(searches)
    return Promise.resolve(alerts)
  })
}

describe('AlertsPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPost.mockReset()
  })

  it('renders saved searches and the alert feed', async () => {
    mockLists()
    render(
      <MemoryRouter>
        <AlertsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: 'Metformin' })).toHaveAttribute(
      'href',
      '/search?q=metformin&stance=support',
    )
    const alertLink = await screen.findByRole('link', {
      name: /gained 2 new supporting/i,
    })
    expect(alertLink).toHaveAttribute('href', '/papers/work_1')
    expect(screen.getByText('New supporting citation')).toBeInTheDocument()
  })

  it('runs all monitors via Check now', async () => {
    mockLists()
    mockedPost.mockResolvedValue({ created_count: 3, alerts: [] })
    render(
      <MemoryRouter>
        <AlertsPage />
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /check now/i }))
    expect(mockedPost).toHaveBeenCalledWith('/alerts/run')
    expect(await screen.findByText(/3 new alert/i)).toBeInTheDocument()
  })

  it('marks an alert read', async () => {
    mockLists()
    mockedPost.mockResolvedValue({ ...ALERTS[0], is_read: true })
    render(
      <MemoryRouter>
        <AlertsPage />
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /^mark read$/i }))
    expect(mockedPost).toHaveBeenCalledWith('/alerts/alrt_1/read')
  })
})
