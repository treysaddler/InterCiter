import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import RelationList from './RelationList'
import type { RelationAssertionView } from '../api/types'

function relation(overrides: Partial<RelationAssertionView> = {}): RelationAssertionView {
  return {
    assertion_id: 'rel_1',
    citing_occurrence_id: 'occ_1',
    citation_mention_id: null,
    evidence_passage_id: null,
    cited_work_id: null,
    target_interpretation_id: null,
    target_candidates: [],
    function: 'direct_evidence',
    stance: 'support',
    scope: null,
    resolution: 'claim_resolved',
    target_link_score: 0.5,
    stance_distribution: null,
    extraction_run_id: 'run_1',
    status: 'active',
    ...overrides,
  }
}

function renderList(relations: RelationAssertionView[]) {
  return render(
    <MemoryRouter>
      <RelationList relations={relations} />
    </MemoryRouter>,
  )
}

describe('RelationList', () => {
  it('renders function and stance as separate tags', () => {
    renderList([relation()])
    expect(screen.getByText(/function: direct_evidence/)).toBeInTheDocument()
    expect(screen.getByText(/stance: support/)).toBeInTheDocument()
  })

  it('links to the matched claim when a target interpretation exists', () => {
    renderList([relation({ target_interpretation_id: 'interp_9' })])
    const link = screen.getByRole('link', { name: /matched claim/i })
    expect(link).toHaveAttribute('href', '/claims/interp_9')
  })

  it('links to the cited paper and labels it paper-level when only a work is resolved', () => {
    renderList([
      relation({
        target_interpretation_id: null,
        cited_work_id: 'work_7',
        resolution: 'paper_resolved',
      }),
    ])
    expect(screen.getByRole('link', { name: /cited paper/i })).toHaveAttribute(
      'href',
      '/papers/work_7',
    )
    expect(screen.getByText(/not a specific claim/i)).toBeInTheDocument()
  })

  it('shows an explicit abstained state when unresolved with no target', () => {
    renderList([
      relation({
        resolution: 'unresolved',
        target_interpretation_id: null,
        cited_work_id: null,
        function: null,
        stance: null,
        target_link_score: null,
      }),
    ])
    expect(screen.getByText(/Abstained/)).toBeInTheDocument()
  })

  it('badges a non-active assertion status (e.g. stale_pending_review)', () => {
    renderList([relation({ status: 'stale_pending_review' })])
    expect(screen.getByText('stale_pending_review')).toBeInTheDocument()
  })

  it('renders an empty state when there are no relations', () => {
    renderList([])
    expect(screen.getByText(/No cited relationships/)).toBeInTheDocument()
  })
})
