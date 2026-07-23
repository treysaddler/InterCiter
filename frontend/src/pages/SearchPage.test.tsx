import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SearchPage from './SearchPage'
import type { SearchResults } from '../api/types'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

// Auth is mocked per-test; default anonymous so the save affordance is hidden.
const mockStatus = vi.fn(() => 'anonymous')
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ status: mockStatus() }),
}))

// The inline network is lazy + d3-heavy; stub it so the page tests stay light.
vi.mock('../components/SearchNetwork', () => ({
  default: ({ workId }: { workId: string }) => (
    <div data-testid="search-network">network:{workId}</div>
  ),
}))

const mockedGet = vi.mocked(api.get)
const mockedPost = vi.mocked(api.post)

function results(overrides: Partial<SearchResults> = {}): SearchResults {
  return {
    query: 'metformin',
    total: 1,
    limit: 25,
    offset: 0,
    hits: [
      {
        claim_id: 'interp_1',
        normalized_text: 'metformin reduced fasting glucose in adults with prediabetes',
        occurrence_id: 'occ_1',
        interpretation_id: 'interp_1',
        work_id: 'work_1',
        paper_title: 'A metformin trial',
        year: 2021,
        section: 'Results',
        function: ['direct_evidence'],
        stance: ['support'],
        resolution: ['claim_resolved'],
        evidence: {
          passage_id: 'pas_1',
          paper_version_id: 'ver_1',
          work_id: 'work_1',
          section: 'Results',
          verbatim_text: 'metformin reduced fasting glucose in adults with prediabetes.',
          char_start: 0,
          char_end: 60,
        },
      },
    ],
    facets: {
      section: { Results: 1 },
      function: { direct_evidence: 1 },
      stance: { support: 1 },
      resolution: { claim_resolved: 1 },
    },
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SearchPage />
    </MemoryRouter>,
  )
}

describe('SearchPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPost.mockReset()
    mockStatus.mockReturnValue('anonymous')
  })

  it('shows example searches when there is no query or facet', () => {
    renderAt('/search')
    expect(
      screen.getByRole('region', { name: /example searches/i }),
    ).toBeInTheDocument()
    // Should not have queried the search endpoint with an empty screen.
    expect(mockedGet).not.toHaveBeenCalled()
  })

  it('renders result cards with provenance and separate function/stance facets', async () => {
    mockedGet.mockResolvedValue(results())
    renderAt('/search?q=metformin')

    expect(mockedGet).toHaveBeenCalledWith('/search/claims?q=metformin')

    // Claim text links to the standalone claim route.
    const claimLink = await screen.findByRole('link', {
      name: /metformin reduced fasting glucose/i,
    })
    expect(claimLink).toHaveAttribute('href', '/claims/interp_1')

    // Verbatim provenance snippet is shown.
    expect(screen.getByText(/“metformin reduced fasting glucose/i)).toBeInTheDocument()

    // Function and stance appear as separate tags (also listed as facet options),
    // so both the facet panel and the result card render them.
    expect(screen.getAllByText('direct evidence').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('support').length).toBeGreaterThanOrEqual(1)

    // The citation network for the top result appears inline with the results.
    expect(await screen.findByTestId('search-network')).toHaveTextContent('work_1')

    // A link promotes the focused result into the full network explorer (UX-2 / G2).
    expect(
      screen.getByRole('link', { name: /full network explorer/i }),
    ).toHaveAttribute('href', '/graph/papers/work_1')
  })

  it('passes facet filters through to the search endpoint', async () => {
    mockedGet.mockResolvedValue(results({ total: 1 }))
    renderAt('/search?q=glucose&stance=support')
    expect(mockedGet).toHaveBeenCalledWith('/search/claims?q=glucose&stance=support')
    await screen.findByText(/1 matching claim/i)
  })

  it('lets an authenticated user save the current search', async () => {
    mockStatus.mockReturnValue('authenticated')
    mockedGet.mockResolvedValue(results())
    mockedPost.mockResolvedValue({ saved_search_id: 'ssch_1' })
    renderAt('/search?q=metformin&stance=support')

    const saveButton = await screen.findByRole('button', { name: /save this search/i })
    saveButton.click()

    expect(mockedPost).toHaveBeenCalledWith('/saved-searches', {
      name: 'metformin',
      query: {
        q: 'metformin',
        section: null,
        function: null,
        stance: 'support',
        resolution: null,
      },
    })
  })
})
