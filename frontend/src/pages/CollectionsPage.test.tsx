import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CollectionsPage from './CollectionsPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)

describe('CollectionsPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('fetches and renders existing collections', async () => {
    mockedGet.mockResolvedValue([
      {
        collection_id: 'coll_1',
        owner_id: 'user_1',
        name: 'Core diabetes papers',
        description: 'priority evidence set',
        member_count: 3,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])

    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<CollectionsPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(mockedGet).toHaveBeenCalledWith('/collections')
    expect(await screen.findByRole('link', { name: /core diabetes papers/i })).toHaveAttribute(
      'href',
      '/collections/coll_1',
    )
  })
})
