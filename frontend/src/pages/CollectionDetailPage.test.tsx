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
const mockedPost = vi.mocked(api.post)

describe('CollectionDetailPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPatch.mockReset()
    mockedDel.mockReset()
    mockedPost.mockReset()
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
      aggregate_citation_tallies: {
        total: 2,
        by_stance: { support: 2 },
        by_function: { direct_evidence: 2 },
        by_resolution: { claim_resolved: 2 },
        by_section: { Results: 2 },
        abstained: 0,
      },
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

    expect(mockedGet).toHaveBeenCalledWith(
      '/collections/coll_1?include_member_tallies=true',
    )
    expect(await screen.findByRole('link', { name: /a metformin trial/i })).toHaveAttribute(
      'href',
      '/papers/work_1',
    )
    expect(screen.getByRole('link', { name: 'Report' })).toHaveAttribute(
      'href',
      '/papers/work_1/report',
    )
    expect(screen.getByRole('link', { name: 'Graph' })).toHaveAttribute(
      'href',
      '/graph/papers/work_1',
    )
    expect(screen.getByText(/citation tallies/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /collection citation summary/i })).toBeInTheDocument()
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
      aggregate_citation_tallies: null,
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
      aggregate_citation_tallies: null,
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
    expect(screen.getByText(/ready to import: 1 doi\(s\), 1 pmid\(s\)/i)).toBeInTheDocument()
  })

  it('keeps semicolon DOIs intact and skips year-like numbers in the preview', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: null,
      members: [],
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const wileyDoi = '10.1002/(sici)1097-4636(199905)45:2<133::aid-jbm9>3.0.co;2-#'
    fireEvent.change(await screen.findByLabelText('Identifiers'), {
      target: { value: `${wileyDoi.toUpperCase()} 2021 pmid:123456` },
    })

    expect(screen.getByText(/ready to import: 1 doi\(s\), 1 pmid\(s\)/i)).toBeInTheDocument()
    expect(screen.getByText(`DOI ${wileyDoi}`)).toBeInTheDocument()
    expect(screen.getByText('PMID 123456')).toBeInTheDocument()
  })

  it('shows rich import feedback after adding members', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: null,
      members: [],
    })
    mockedPost.mockResolvedValue({
      collection_id: 'coll_1',
      added_count: 3,
      skipped_identifiers: ['bad-id'],
      created_stub_work_ids: ['work_stub_1'],
      members: [],
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.change(await screen.findByLabelText('Identifiers'), {
      target: { value: '10.1000/example 12345678 bad-id' },
    })
    fireEvent.click(screen.getByRole('button', { name: /add members/i }))

    expect(mockedPost).toHaveBeenCalledWith('/collections/coll_1/members', {
      csv_text: '10.1000/example 12345678 bad-id',
      dois: ['10.1000/example'],
      pmids: ['12345678'],
    })
    expect(
      await screen.findByText(/added 3 member\(s\); 1 created as metadata stubs; 1 skipped/i),
    ).toBeInTheDocument()
  })

  it('sorts members client-side without refetching', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: {
        total: 2,
        by_stance: { support: 2 },
        by_function: { direct_evidence: 2 },
        by_resolution: { claim_resolved: 2 },
        by_section: { Results: 2 },
        abstained: 0,
      },
      members: [
        {
          collection_membership_id: 'cmem_1',
          work_id: 'work_1',
          title: 'A metformin trial',
          doi: '10.1000/example-a',
          pmid: null,
          year: 2021,
          added_at: '2026-01-03T00:00:00Z',
          citation_tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
            abstained: 0,
          },
        },
        {
          collection_membership_id: 'cmem_2',
          work_id: 'work_2',
          title: 'A semaglutide trial',
          doi: '10.1000/example-b',
          pmid: null,
          year: 2022,
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

    await screen.findByLabelText('Sort members')
    // Default order: most recently added first.
    let titles = screen.getAllByRole('link', { name: /trial/i })
    expect(titles[0]).toHaveTextContent('A metformin trial')

    fireEvent.change(screen.getByLabelText('Sort members'), {
      target: { value: 'support_desc' },
    })

    titles = screen.getAllByRole('link', { name: /trial/i })
    expect(titles[0]).toHaveTextContent('A semaglutide trial')
    // Sorting is client-side: no additional fetch beyond the initial load
    // (the collection detail plus the new-citations delta).
    expect(mockedGet).toHaveBeenCalledTimes(2)
  })

  it('filters members by identifier text', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: {
        total: 1,
        by_stance: { support: 1 },
        by_function: { direct_evidence: 1 },
        by_resolution: { claim_resolved: 1 },
        by_section: { Results: 1 },
        abstained: 0,
      },
      members: [
        {
          collection_membership_id: 'cmem_1',
          work_id: 'work_1',
          title: 'A metformin trial',
          doi: '10.1000/example-a',
          pmid: null,
          year: 2021,
          added_at: '2026-01-01T00:00:00Z',
          citation_tallies: {
            total: 1,
            by_stance: { support: 1 },
            by_function: { direct_evidence: 1 },
            by_resolution: { claim_resolved: 1 },
            by_section: { Results: 1 },
            abstained: 0,
          },
        },
        {
          collection_membership_id: 'cmem_2',
          work_id: 'work_2',
          title: 'A semaglutide trial',
          doi: '10.1000/example-b',
          pmid: null,
          year: 2022,
          added_at: '2026-01-02T00:00:00Z',
          citation_tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
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

    await screen.findByRole('link', { name: /a metformin trial/i })
    fireEvent.change(screen.getByLabelText('Filter members'), {
      target: { value: 'example-b' },
    })

    expect(screen.queryByRole('link', { name: /a metformin trial/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /a semaglutide trial/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Filter members'), {
      target: { value: 'not-a-match' },
    })
    expect(screen.getByText(/no members match this filter/i)).toBeInTheDocument()
  })

  it('exports collection members as CSV', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: {
        total: 1,
        by_stance: { support: 1 },
        by_function: { direct_evidence: 1 },
        by_resolution: { claim_resolved: 1 },
        by_section: { Results: 1 },
        abstained: 0,
      },
      members: [
        {
          collection_membership_id: 'cmem_1',
          work_id: 'work_1',
          title: 'A metformin trial, "phase 3"',
          doi: '10.1000/example-a',
          pmid: '12345',
          year: 2021,
          added_at: '2026-01-01T00:00:00Z',
          citation_tallies: {
            total: 1,
            by_stance: { support: 1 },
            by_function: { direct_evidence: 1 },
            by_resolution: { claim_resolved: 1 },
            by_section: { Results: 1 },
            abstained: 0,
          },
        },
        {
          collection_membership_id: 'cmem_2',
          work_id: 'work_2',
          title: '=SUM(A1:A9)',
          doi: null,
          pmid: '67890',
          year: 2022,
          added_at: '2026-01-02T00:00:00Z',
          citation_tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
            abstained: 0,
          },
        },
      ],
    })

    const createObjectURL = vi.fn((_blob: Blob) => 'blob:test')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
    })
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /export members csv/i }))

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    const blob = createObjectURL.mock.calls[0][0]
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = () => reject(new Error('failed to read blob text'))
      reader.onload = () => resolve(String(reader.result ?? ''))
      reader.readAsText(blob)
    })
    expect(text).toContain('work_id,doi,pmid,title')
    // Every cell is quoted; embedded quotes are doubled per RFC 4180.
    expect(text).toContain(
      '"work_1","10.1000/example-a","12345","A metformin trial, ""phase 3"""',
    )
    // Titles that would execute as spreadsheet formulas are prefixed.
    expect(text).toContain('"work_2","","67890","\'=SUM(A1:A9)"')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    anchorClick.mockRestore()
  })

  it('exports filtered identifiers as TXT', async () => {
    mockedGet.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: 'priority evidence set',
      member_count: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      aggregate_citation_tallies: {
        total: 1,
        by_stance: { support: 1 },
        by_function: { direct_evidence: 1 },
        by_resolution: { claim_resolved: 1 },
        by_section: { Results: 1 },
        abstained: 0,
      },
      members: [
        {
          collection_membership_id: 'cmem_1',
          work_id: 'work_1',
          title: 'A metformin trial',
          doi: '10.1000/example-a',
          pmid: '12345',
          year: 2021,
          added_at: '2026-01-01T00:00:00Z',
          citation_tallies: {
            total: 1,
            by_stance: { support: 1 },
            by_function: { direct_evidence: 1 },
            by_resolution: { claim_resolved: 1 },
            by_section: { Results: 1 },
            abstained: 0,
          },
        },
        {
          collection_membership_id: 'cmem_2',
          work_id: 'work_2',
          title: 'A semaglutide trial',
          doi: '10.1000/example-b',
          pmid: null,
          year: 2022,
          added_at: '2026-01-02T00:00:00Z',
          citation_tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
            abstained: 0,
          },
        },
      ],
    })

    const createObjectURL = vi.fn((_blob: Blob) => 'blob:test')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
    })
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByRole('link', { name: /a metformin trial/i })
    fireEvent.change(screen.getByLabelText('Filter members'), {
      target: { value: 'example-a' },
    })
    fireEvent.click(screen.getByRole('button', { name: /export identifiers txt/i }))

    const blob = createObjectURL.mock.calls[0][0]
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = () => reject(new Error('failed to read blob text'))
      reader.onload = () => resolve(String(reader.result ?? ''))
      reader.readAsText(blob)
    })
    expect(text).toBe('10.1000/example-a\n12345\n')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    anchorClick.mockRestore()
  })

  it('renders integrity badges for flagged members', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.includes('/new-citations')) {
        return Promise.resolve({
          collection_id: 'coll_1',
          has_snapshot: false,
          snapshot_at: null,
          new_support_total: 0,
          new_contradict_total: 0,
          members: [],
        })
      }
      return Promise.resolve({
        collection_id: 'coll_1',
        owner_id: 'user_1',
        name: 'Core diabetes papers',
        description: null,
        member_count: 1,
        is_watched: false,
        watch_snapshot_at: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        aggregate_citation_tallies: null,
        members: [
          {
            collection_membership_id: 'cmem_1',
            work_id: 'work_1',
            title: 'A retracted trial',
            doi: '10.1000/example',
            pmid: null,
            year: 2021,
            added_at: '2026-01-01T00:00:00Z',
            citation_tallies: null,
            is_retracted: true,
            integrity_notice: 'expression_of_concern',
          },
        ],
      })
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Retracted')).toBeInTheDocument()
    expect(screen.getByText('expression of concern')).toBeInTheDocument()
  })

  it('toggles watch state and captures a baseline', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.includes('/new-citations')) {
        return Promise.resolve({
          collection_id: 'coll_1',
          has_snapshot: true,
          snapshot_at: '2026-01-02T00:00:00Z',
          new_support_total: 2,
          new_contradict_total: 0,
          members: [
            {
              work_id: 'work_1',
              title: 'A metformin trial',
              new_support: 2,
              new_contradict: 0,
            },
          ],
        })
      }
      return Promise.resolve({
        collection_id: 'coll_1',
        owner_id: 'user_1',
        name: 'Core diabetes papers',
        description: null,
        member_count: 0,
        is_watched: false,
        watch_snapshot_at: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        aggregate_citation_tallies: null,
        members: [],
      })
    })
    mockedPost.mockResolvedValue({
      collection_id: 'coll_1',
      owner_id: 'user_1',
      name: 'Core diabetes papers',
      description: null,
      member_count: 0,
      is_watched: true,
      watch_snapshot_at: '2026-01-03T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-03T00:00:00Z',
    })

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    // The delta panel renders newly observed signals from the baseline.
    expect(await screen.findByText(/new since baseline/i)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /a metformin trial/i }),
    ).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /watch this collection/i }),
    )
    expect(mockedPost).toHaveBeenCalledWith('/collections/coll_1/watch', {
      watch: true,
    })
    expect(
      await screen.findByText(/now watching this collection/i),
    ).toBeInTheDocument()
  })

  it('bulk-removes the filtered members after confirmation', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.includes('/new-citations')) {
        return Promise.resolve({
          collection_id: 'coll_1',
          has_snapshot: false,
          snapshot_at: null,
          new_support_total: 0,
          new_contradict_total: 0,
          members: [],
        })
      }
      return Promise.resolve({
        collection_id: 'coll_1',
        owner_id: 'user_1',
        name: 'Core diabetes papers',
        description: null,
        member_count: 2,
        is_watched: false,
        watch_snapshot_at: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        aggregate_citation_tallies: null,
        members: [
          {
            collection_membership_id: 'cmem_1',
            work_id: 'work_1',
            title: 'A metformin trial',
            doi: '10.1000/example-a',
            pmid: null,
            year: 2021,
            added_at: '2026-01-01T00:00:00Z',
            citation_tallies: null,
            is_retracted: null,
            integrity_notice: null,
          },
          {
            collection_membership_id: 'cmem_2',
            work_id: 'work_2',
            title: 'A semaglutide trial',
            doi: '10.1000/example-b',
            pmid: null,
            year: 2022,
            added_at: '2026-01-02T00:00:00Z',
            citation_tallies: null,
            is_retracted: null,
            integrity_notice: null,
          },
        ],
      })
    })
    mockedPost.mockResolvedValue({
      collection_id: 'coll_1',
      removed_count: 1,
      removed_work_ids: ['work_1'],
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(
      <MemoryRouter initialEntries={['/collections/coll_1']}>
        <Routes>
          <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByRole('link', { name: /a metformin trial/i })
    fireEvent.change(screen.getByLabelText('Filter members'), {
      target: { value: 'example-a' },
    })
    // Only one member matches the filter now.
    fireEvent.click(
      screen.getByRole('button', { name: /remove 1 filtered member/i }),
    )

    expect(mockedPost).toHaveBeenCalledWith('/collections/coll_1/members/bulk-delete', {
      work_ids: ['work_1'],
    })
    expect(await screen.findByText(/removed 1 member/i)).toBeInTheDocument()
  })
})
