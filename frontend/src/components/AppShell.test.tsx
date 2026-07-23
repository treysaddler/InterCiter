import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import AppShell from './AppShell'

// Controllable auth state for the mocked provider.
let mockAuth: { status: string; user: unknown; logout: () => Promise<void> }

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

function renderShell() {
  return render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  )
}

describe('AppShell grouped nav', () => {
  it('shows Search + Explore and hides auth-only areas when anonymous', () => {
    mockAuth = { status: 'anonymous', user: null, logout: vi.fn() }
    renderShell()

    expect(screen.getByRole('link', { name: 'Search' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Explore' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument()

    // Workspaces + write areas are only for authenticated users.
    expect(
      screen.queryByRole('button', { name: 'Workspaces' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Submit a paper' }),
    ).not.toBeInTheDocument()
  })

  it('gives the Network explorer a home inside the Explore group', async () => {
    const user = userEvent.setup()
    mockAuth = { status: 'anonymous', user: null, logout: vi.fn() }
    renderShell()

    // Closed submenu items are hidden; open Explore to reveal them.
    await user.click(screen.getByRole('button', { name: 'Explore' }))
    expect(
      screen.getByRole('link', { name: 'Network explorer' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Papers' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analytics' })).toBeInTheDocument()
  })

  it('shows Workspaces + Submit for an authenticated non-reviewer, but not Review', () => {
    mockAuth = {
      status: 'authenticated',
      user: { display_name: 'Ann', role: 'author' },
      logout: vi.fn(),
    }
    renderShell()

    expect(screen.getByRole('button', { name: 'Workspaces' })).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Submit a paper' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Account' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sign out/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Review' })).not.toBeInTheDocument()
  })

  it('shows Review for a reviewer', () => {
    mockAuth = {
      status: 'authenticated',
      user: { display_name: 'Rae', role: 'reviewer' },
      logout: vi.fn(),
    }
    renderShell()

    expect(screen.getByRole('link', { name: 'Review' })).toBeInTheDocument()
  })
})
