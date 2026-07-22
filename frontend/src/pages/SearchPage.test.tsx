import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SearchPage from './SearchPage'
import type { SearchResults } from '../api/types'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)

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
  })

  it('passes facet filters through to the search endpoint', async () => {
    mockedGet.mockResolvedValue(results({ total: 1 }))
    renderAt('/search?q=glucose&stance=support')
    expect(mockedGet).toHaveBeenCalledWith('/search/claims?q=glucose&stance=support')
    await screen.findByText(/1 matching claim/i)
  })
})
