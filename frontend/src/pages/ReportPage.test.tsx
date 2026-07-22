import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ReportPage from './ReportPage'
import type { PaperReport } from '../api/types'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)

function sampleReport(overrides: Partial<PaperReport> = {}): PaperReport {
  return {
    work_id: 'work_1',
    total_statements: 2,
    filtered_statements: 2,
    facets: {
      section: { Results: 2 },
      function: { direct_evidence: 2 },
      stance: { support: 2 },
      resolution: { claim_resolved: 2 },
      year: { '2021': 2 },
    },
    applied_filters: {
      section: null,
      function: null,
      stance: null,
      resolution: null,
      min_year: null,
      max_year: null,
    },
    tallies: {
      total: 2,
      by_stance: { support: 2 },
      by_function: { direct_evidence: 2 },
      by_resolution: { claim_resolved: 2 },
      by_section: { Results: 2 },
      abstained: 0,
    },
    timeline: [{ year: 2021, statement_count: 2, citing_work_count: 1 }],
    conflict_summary: {
      has_conflicting_stances: false,
      supporting_statements: 2,
      contradicting_statements: 0,
      neutral_or_unclear_statements: 0,
      conflicting_citing_work_count: 0,
    },
    statements: [
      {
        assertion_id: 'rel_1',
        citing_work_id: 'work_2',
        citing_claim_id: 'interp_2',
        function: 'direct_evidence',
        stance: 'support',
        resolution: 'claim_resolved',
        status: 'accepted',
        section: 'Results',
        evidence: {
          passage_id: 'pas_1',
          paper_version_id: 'ver_1',
          work_id: 'work_2',
          section: 'Results',
          verbatim_text: 'metformin reduced fasting glucose in adults with prediabetes.',
          char_start: 0,
          char_end: 60,
        },
      },
    ],
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/papers/:workId/report" element={<ReportPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ReportPage', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('fetches and renders report sections', async () => {
    mockedGet.mockResolvedValue(sampleReport())
    renderAt('/papers/work_1/report')

    expect(mockedGet).toHaveBeenCalledWith('/papers/work_1/report')
    expect(await screen.findByText(/citation report/i)).toBeInTheDocument()
    expect(screen.getByText(/2 of 2 citing statements shown/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /citations over time/i })).toBeInTheDocument()
    expect(screen.getByText('2021')).toBeInTheDocument()
  })

  it('passes filters in the request query', async () => {
    mockedGet.mockResolvedValue(sampleReport())
    renderAt('/papers/work_1/report?stance=support&section=Results')

    expect(mockedGet).toHaveBeenCalledWith(
      '/papers/work_1/report?section=Results&stance=support',
    )
    await screen.findByText(/2 of 2 citing statements shown/i)
  })
})
