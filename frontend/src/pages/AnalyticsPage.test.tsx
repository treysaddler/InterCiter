import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalyticsPage from './AnalyticsPage'
import type { BibliometricsSummary } from '../api/types'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)

function sampleSummary(overrides: Partial<BibliometricsSummary> = {}): BibliometricsSummary {
  return {
    document_count: 4,
    source_count: 2,
    author_count: 3,
    author_appearances: 7,
    co_authors_per_doc: 1.75,
    single_authored_count: 2,
    min_year: 2019,
    max_year: 2022,
    annual_growth_rate: 0,
    avg_citations_per_doc: 1,
    total_citations: 4,
    documents_without_year: 0,
    annual_production: [
      { year: 2019, document_count: 1 },
      { year: 2020, document_count: 1 },
      { year: 2021, document_count: 1 },
      { year: 2022, document_count: 1 },
    ],
    top_authors: [{ name: 'Ada Lovelace', document_count: 3 }],
    top_sources: [{ source: 'Journal A', document_count: 2 }],
    top_cited_documents: [
      { work_id: 'w1', title: 'Alpha', year: 2019, citation_count: 3 },
    ],
    ...overrides,
  }
}

describe('AnalyticsPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('renders the Main Information dashboard from the summary', async () => {
    mockedGet.mockResolvedValue(sampleSummary())
    render(
      <MemoryRouter initialEntries={['/analytics']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('2019–2022')).toBeInTheDocument()
    // Indicator cards + rank tables are the source of truth (not the bars).
    expect(screen.getByText('Timespan')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('Journal A')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute(
      'href',
      '/papers/w1',
    )
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/summary')
  })

  it('shows an empty state when the cohort has no documents', async () => {
    mockedGet.mockResolvedValue(
      sampleSummary({
        document_count: 0,
        source_count: 0,
        author_count: 0,
        min_year: null,
        max_year: null,
        annual_growth_rate: null,
        annual_production: [],
        top_authors: [],
        top_sources: [],
        top_cited_documents: [],
      }),
    )
    render(
      <MemoryRouter initialEntries={['/analytics']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/No documents match this cohort/)).toBeInTheDocument()
  })

  it('passes the year filter through to the endpoint', async () => {
    mockedGet.mockResolvedValue(sampleSummary())
    render(
      <MemoryRouter initialEntries={['/analytics?min_year=2020']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    await screen.findByText('2019–2022')
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/summary?min_year=2020')
  })
})
