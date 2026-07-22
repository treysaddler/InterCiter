import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  GovBanner,
  GridContainer,
  Header,
  NavMenuButton,
  PrimaryNav,
  Title,
} from '@trussworks/react-uswds'

import PageFocus from './PageFocus'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/search', label: 'Search' },
  { to: '/ingest', label: 'Submit a paper', authOnly: true },
  { to: '/review', label: 'Review', authOnly: true },
  { to: '/account', label: 'Account', authOnly: true },
]

export default function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const { status, user, logout } = useAuth()
  const navigate = useNavigate()

  async function onSignOut() {
    await logout()
    setMobileNavOpen(false)
    navigate('/')
  }

  const authenticated = status === 'authenticated' && Boolean(user)

  const navItems = NAV.filter((item) => !item.authOnly || authenticated).map(
    (item) => (
      <NavLink
        key={item.to}
        to={item.to}
        className="usa-nav__link"
        onClick={() => setMobileNavOpen(false)}
      >
        <span>{item.label}</span>
      </NavLink>
    ),
  )

  navItems.push(
    authenticated && user ? (
      <button
        key="signout"
        type="button"
        className="usa-nav__link usa-button usa-button--unstyled"
        onClick={onSignOut}
      >
        <span>Sign out ({user.display_name})</span>
      </button>
    ) : (
      <NavLink
        key="signin"
        to="/login"
        className="usa-nav__link"
        onClick={() => setMobileNavOpen(false)}
      >
        <span>Sign in</span>
      </NavLink>
    ),
  )

  return (
    <>
      <a className="usa-skipnav" href="#main-content">
        Skip to main content
      </a>

      <GovBanner />

      <div
        className={`usa-overlay${mobileNavOpen ? ' is-visible' : ''}`}
        onClick={() => setMobileNavOpen(false)}
      />

      <Header basic>
        <div className="usa-nav-container">
          <div className="usa-navbar">
            <Title>
              <Link to="/">InterCiter</Link>
            </Title>
            <NavMenuButton
              label="Menu"
              onClick={() => setMobileNavOpen((open) => !open)}
            />
          </div>
          <PrimaryNav
            items={navItems}
            mobileExpanded={mobileNavOpen}
            onToggleMobileNav={() => setMobileNavOpen((open) => !open)}
          />
        </div>
      </Header>

      <PageFocus />

      <main id="main-content" tabIndex={-1}>
        <GridContainer className="padding-bottom-6">
          <Outlet />
        </GridContainer>
      </main>

      <footer className="usa-footer usa-footer--slim">
        <div className="usa-footer__secondary-section">
          <GridContainer>
            <p className="usa-footer__logo-heading">InterCiter</p>
            <p className="font-body-3xs text-base">
              Provenance-first exploration and review of scientific claims. A client
              of the InterCiter <code>/v1</code> API.
            </p>
          </GridContainer>
        </div>
      </footer>
    </>
  )
}
