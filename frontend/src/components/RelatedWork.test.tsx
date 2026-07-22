import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

// Control the auth status without mounting the real AuthProvider (which probes /users/me).
const authState = vi.hoisted(() => ({ status: 'authenticated' as string }))
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ status: authState.status, user: null }),
}))

import RelatedWork from './RelatedWork'

function renderPanel() {
  return render(
    <MemoryRouter>
      <RelatedWork workId="work_1" />
    </MemoryRouter>,
  )
}

describe('RelatedWork', () => {
  it('offers the discovery action to authenticated users', () => {
    authState.status = 'authenticated'
    renderPanel()
    expect(
      screen.getByRole('button', { name: /Find related work/ }),
    ).toBeInTheDocument()
  })

  it('prompts anonymous users to sign in instead of exposing the action', () => {
    authState.status = 'anonymous'
    renderPanel()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText(/Sign in/)).toBeInTheDocument()
  })
})
