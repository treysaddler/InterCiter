import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CollectionDetailPage from './CollectionDetailPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)
const mockedPatch = vi.mocked(api.patch)
const mockedDel = vi.mocked(api.del)

describe('CollectionDetailPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPatch.mockReset()
    mockedDel.mockReset()
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

  it('saves collection metadata and can delete the collection', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      members: [],
    })
    mockedPatch.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Updated set',
      description: 'updated description',
      member_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    })
    mockedDel.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
          <Route path="/collections" element={<div>collections-list</div>} />
        </Routes>
      </MemoryRouter>,
    )

    const nameInput = await screen.findByLabelText('Name')
    fireEvent.change(nameInput, { target: { value: 'Updated set' } })
    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'updated description' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save details/i }))

    expect(mockedPatch).toHaveBeenCalledWith('/collections/coll_1', {
      name: 'Updated set',
      description: 'updated description',
    })

    fireEvent.click(screen.getByRole('button', { name: /delete collection/i }))
    expect(mockedDel).toHaveBeenCalledWith('/collections/coll_1')
  })

  it('loads identifiers from an uploaded file', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      members: [],
    })

    const file = new File(['10.1000/example\n12345678'], 'ids.csv', {
      type: 'text/csv',
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const fileInput = await screen.findByLabelText('Upload CSV/TXT')
    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(await screen.findByText(/loaded identifiers from ids.csv/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Identifiers')).toHaveValue('10.1000/example\n12345678')
  })
})
