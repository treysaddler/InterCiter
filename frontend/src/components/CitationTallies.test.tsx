import { render, screen } from '@testing-library/react'

import CitationTallies from './CitationTallies'
import type { CitationTallies as Tallies } from '../api/types'

function tallies(over: Partial<Tallies> = {}): Tallies {
  return {
    total: 0,
    by_stance: {},
    by_function: {},
    by_resolution: {},
    by_section: {},
    abstained: 0,
    ...over,
  }
}

describe('CitationTallies', () => {
  it('renders the total and per-dimension counts', () => {
    render(
      <CitationTallies
        tallies={tallies({
          total: 3,
          by_stance: { support: 2, contradict: 1 },
          by_function: { direct_evidence: 3 },
          by_resolution: { claim_resolved: 3 },
          by_section: { Results: 2, Discussion: 1 },
        })}
      />,
    )
    expect(screen.getByText(/citing statements/)).toBeInTheDocument()
    expect(screen.getByText('support')).toBeInTheDocument()
    expect(screen.getByText('contradict')).toBeInTheDocument()
    expect(screen.getByText('direct_evidence')).toBeInTheDocument()
    expect(screen.getByText('Results')).toBeInTheDocument()
  })

  it('surfaces abstention explicitly rather than hiding it', () => {
    render(
      <CitationTallies
        tallies={tallies({ total: 2, by_stance: { support: 1 }, abstained: 1 })}
      />,
    )
    expect(screen.getByText(/abstained \(no function or stance\)/)).toBeInTheDocument()
  })

  it('shows an empty state when nothing cites the subject', () => {
    render(<CitationTallies tallies={tallies()} />)
    expect(screen.getByText(/No citing statements/)).toBeInTheDocument()
  })
})
