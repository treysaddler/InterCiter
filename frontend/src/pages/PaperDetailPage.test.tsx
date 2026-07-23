import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PaperDetailPage from './PaperDetailPage'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

// RelatedWork pulls in useAuth + discovery; stub it so this test stays focused.
vi.mock('../components/RelatedWork', () => ({
  default: () => <div>related-work</div>,
}))

const mockedGet = vi.mocked(api.get)

describe('PaperDetailPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('shows a retraction banner and badge for a retracted paper', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/claims')) return Promise.resolve([])
      if (url.endsWith('/citation-stats')) {
        return Promise.resolve({
          tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
            abstained: 0,
          },
        })
      }
      return Promise.resolve({
        work_id: 'work_1',
        title: 'A retracted trial',
        authors: ['A. Author'],
        venue: 'Journal',
        year: 2019,
        doi: '10.1000/example',
        pmid: null,
        s2_corpus_id: null,
        availability_state: 'metadata_stub',
        is_retracted: true,
        integrity_notice: 'expression_of_concern',
      })
    })

    render(
      <MemoryRouter initialEntries={['/papers/work_1']}>
        <Routes>
          <Route path="/papers/:workId" element={<PaperDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(
      await screen.findByText(/this work has been retracted/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Retracted')).toBeInTheDocument()
    expect(screen.getByText('expression of concern')).toBeInTheDocument()
  })

  it('renders the TLDR and collapsible abstract when present', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/claims')) return Promise.resolve([])
      if (url.endsWith('/citation-stats')) {
        return Promise.resolve({
          tallies: {
            total: 0,
            by_stance: {},
            by_function: {},
            by_resolution: {},
            by_section: {},
            abstained: 0,
          },
        })
      }
      return Promise.resolve({
        work_id: 'work_2',
        title: 'An enriched paper',
        authors: [],
        venue: null,
        year: null,
        doi: null,
        pmid: null,
        s2_corpus_id: '12345',
        availability_state: 'metadata_stub',
        is_retracted: null,
        integrity_notice: null,
        tldr: 'One-line gist of the work.',
        abstract: 'The full abstract text.',
      })
    })

    render(
      <MemoryRouter initialEntries={['/papers/work_2']}>
        <Routes>
          <Route path="/papers/:workId" element={<PaperDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText(/one-line gist of the work/i)).toBeInTheDocument()
    expect(screen.getByText('Abstract')).toBeInTheDocument()
    expect(screen.getByText('The full abstract text.')).toBeInTheDocument()
  })
})
