import { render, screen } from '@testing-library/react'

import EvidencePane from './EvidencePane'
import type { EvidenceRef } from '../api/types'

function evidence(overrides: Partial<EvidenceRef> = {}): EvidenceRef {
  return {
    passage_id: 'pas_1',
    paper_version_id: 'ver_1',
    work_id: 'work_1',
    section: 'Results',
    verbatim_text: 'Metformin reduced fasting glucose.',
    char_start: 100,
    char_end: 200,
    ...overrides,
  }
}

describe('EvidencePane', () => {
  it('highlights the span when it is a valid offset into the verbatim text', () => {
    render(<EvidencePane evidence={evidence()} spanStart={0} spanEnd={9} />)
    const mark = screen.getByText('Metformin')
    expect(mark.tagName).toBe('MARK')
  })

  it('renders plain text (no highlight) when the span is out of bounds', () => {
    render(<EvidencePane evidence={evidence()} spanStart={0} spanEnd={9999} />)
    // Whole sentence present as one node; no <mark>.
    expect(screen.getByText('Metformin reduced fasting glucose.')).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('does not highlight when no span is provided', () => {
    render(<EvidencePane evidence={evidence()} />)
    expect(document.querySelector('mark')).toBeNull()
  })

  it('shows the section label and source', () => {
    render(<EvidencePane evidence={evidence()} />)
    expect(screen.getByText('Results')).toBeInTheDocument()
    expect(screen.getByText(/source work_1/)).toBeInTheDocument()
  })
})
