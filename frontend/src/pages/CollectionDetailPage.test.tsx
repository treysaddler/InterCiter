import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CollectionDetailPage from './CollectionDetailPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), del: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)

describe('CollectionDetailPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('requests member tallies and renders member entry', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      members: [
        {
          collection_membership_id: 'cmem_1',
          work_id: 'work_1',
          title: 'A metformin trial',
          doi: '10.1000/example',
          pmid: null,
          year: 2021,
          added_at: '2026-01-01T00:00:00Z',
          citation_tallies: {
            total: 2,
            by_stance: { support: 2 },
            by_function: { direct_evidence: 2 },
            by_resolution: { claim_resolved: 2 },
            by_section: { Results: 2 },
            abstained: 0,
          },
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(mockedGet).toHaveBeenCalledWith('/collections/coll_1?include_member_tallies=true')
    expect(await screen.findByRole('link', { name: /a metformin trial/i })).toHaveAttribute(
      'href',
      '/papers/work_1',
    )
    expect(screen.getByText(/citation tallies/i)).toBeInTheDocument()
  })
})
