import { render, screen } from '@testing-library/react'

import ScoreChips from './ScoreChips'
import type { ScoreComponent } from '../api/types'

function comp(name: string, value: number | null): ScoreComponent {
  return { name, value, assessment_id: null, algorithm_version: null, inputs: null }
}

describe('ScoreChips', () => {
  it('renders one labeled chip per component with its value', () => {
    render(
      <ScoreChips
        components={[comp('extraction_fidelity', 0.7), comp('model_agreement', 0.25)]}
      />,
    )
    expect(screen.getByText('extraction_fidelity')).toBeInTheDocument()
    expect(screen.getByText('0.70')).toBeInTheDocument()
    expect(screen.getByText('0.25')).toBeInTheDocument()
  })

  it('shows "abstained" for a null value rather than faking a number', () => {
    render(<ScoreChips components={[comp('target_link', null)]} />)
    expect(screen.getByText('abstained')).toBeInTheDocument()
  })

  it('handles an empty component set', () => {
    render(<ScoreChips components={[]} />)
    expect(screen.getByText(/No score components/)).toBeInTheDocument()
  })
})
