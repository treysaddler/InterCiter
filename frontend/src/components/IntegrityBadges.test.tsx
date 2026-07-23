import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import IntegrityBadges from './IntegrityBadges'

describe('IntegrityBadges', () => {
  it('renders a retracted badge', () => {
    render(<IntegrityBadges isRetracted integrityNotice={null} />)
    expect(screen.getByText('Retracted')).toBeInTheDocument()
  })

  it('renders an editorial notice, humanizing underscores', () => {
    render(
      <IntegrityBadges isRetracted={false} integrityNotice="expression_of_concern" />,
    )
    expect(screen.getByText('expression of concern')).toBeInTheDocument()
    expect(screen.queryByText('Retracted')).not.toBeInTheDocument()
  })

  it('renders nothing when there is no integrity signal', () => {
    const { container } = render(
      <IntegrityBadges isRetracted={null} integrityNotice={null} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
