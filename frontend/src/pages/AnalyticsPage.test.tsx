import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalyticsPage from './AnalyticsPage'
import type {
  AuthorMetrics,
  BibliometricsSummary,
  CountryMetrics,
  SourceMetrics,
} from '../api/types'
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

const authorMetrics: AuthorMetrics = {
  author_count: 3,
  authors: [{ name: 'Ada Lovelace', document_count: 3, total_citations: 4, h_index: 1 }],
  lotka: {
    coefficient: 1.71,
    constant: 4,
    author_count: 3,
    points: [
      { documents_written: 2, author_count: 2, proportion: 0.6667 },
      { documents_written: 3, author_count: 1, proportion: 0.3333 },
    ],
  },
}

const sourceMetrics: SourceMetrics = {
  source_count: 2,
  sources: [
    {
      source: 'Journal A',
      document_count: 2,
      total_citations: 4,
      h_index: 1,
      bradford_zone: 1,
    },
  ],
  bradford_zones: [
    { zone: 1, source_count: 1, article_count: 2 },
    { zone: 2, source_count: 0, article_count: 0 },
    { zone: 3, source_count: 1, article_count: 2 },
  ],
}

/** Route the mock by URL so each tab's panel resolves the right shape. */
function routeByUrl(url: string) {
  if (url.startsWith('/cohorts/resolve'))
    return Promise.resolve({
      source_type: url.includes('map=') ? 'map' : 'collection',
      source_id: 'x',
      name: url.includes('map=') ? 'My map' : 'Core diabetes',
      member_count: 2,
    })
  if (url.startsWith('/bibliometrics/authors')) return Promise.resolve(authorMetrics)
  if (url.startsWith('/bibliometrics/sources')) return Promise.resolve(sourceMetrics)
  if (url.startsWith('/bibliometrics/countries'))
    return Promise.resolve({
      country_count: 0,
      documents_with_country: 0,
      international_co_authorship_pct: null,
      countries: [],
    } as CountryMetrics)
  return Promise.resolve(sampleSummary())
}

describe('AnalyticsPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('renders the Main Information overview from the summary', async () => {
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('2019–2022')).toBeInTheDocument()
    expect(screen.getByText('Timespan')).toBeInTheDocument()
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
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics?min_year=2020']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    await screen.findByText('2019–2022')
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/summary?min_year=2020')
  })

  it('forwards a saved-collection cohort and shows the cohort banner', async () => {
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics?collection=coll_1']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('2019–2022')).toBeInTheDocument()
    expect(mockedGet).toHaveBeenCalledWith(
      '/bibliometrics/summary?collection=coll_1',
    )
    // The banner names the cohort and offers a way back to the whole corpus.
    expect(screen.getByText(/Analyzing a saved collection/)).toBeInTheDocument()
    expect(screen.getByText('Core diabetes')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Analyze the full corpus/ }),
    ).toHaveAttribute('href', '/analytics')
  })

  it('renders author metrics (h-index + Lotka) on the Authors tab', async () => {
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics?tab=authors']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'h-index' })).toBeInTheDocument()
    expect(screen.getByText(/Fitted exponent n = 1.71/)).toBeInTheDocument()
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/authors')
  })

  it('renders Bradford zones on the Sources tab', async () => {
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics?tab=sources']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText("Bradford's law zones")).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Bradford zone' })).toBeInTheDocument()
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/sources')
  })

  it('explains missing affiliation data on the Countries tab', async () => {
    mockedGet.mockImplementation((url: string) => routeByUrl(url))
    render(
      <MemoryRouter initialEntries={['/analytics?tab=countries']}>
        <AnalyticsPage />
      </MemoryRouter>,
    )

    expect(
      await screen.findByText(/No affiliation\/country metadata is available/),
    ).toBeInTheDocument()
    expect(mockedGet).toHaveBeenCalledWith('/bibliometrics/countries')
  })
})
