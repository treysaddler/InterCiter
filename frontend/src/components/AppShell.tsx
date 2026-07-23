import { Fragment, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  GridContainer,
  Header,
  Menu,
  NavDropDownButton,
  NavMenuButton,
  PrimaryNav,
  Title,
} from '@trussworks/react-uswds'

import PageFocus from './PageFocus'
import { useAuth } from '../auth/AuthContext'

interface NavLeaf {
  to: string
  label: string
}

interface NavGroup {
  label: string
  menuId: string
  items: NavLeaf[]
}

/**
 * Goal-oriented information architecture (plans/ux-journeys.md §4).
 * `Explore` gathers the open "understand the literature" surfaces — including the
 * Network explorer, which previously had no nav home. `Workspaces` gathers the
 * things an authenticated user owns and monitors. Grouping keeps the primary nav
 * small as parity features land inside a group rather than adding top-level items.
 */
const EXPLORE: NavGroup = {
  label: 'Explore',
  menuId: 'explore-menu',
  items: [
    { to: '/papers', label: 'Papers' },
    { to: '/graph', label: 'Network explorer' },
    { to: '/analytics', label: 'Analytics' },
  ],
}

const WORKSPACES: NavGroup = {
  label: 'Workspaces',
  menuId: 'workspaces-menu',
  items: [
    { to: '/collections', label: 'Collections' },
    { to: '/maps', label: 'Maps' },
    { to: '/alerts', label: 'Alerts' },
  ],
}

export default function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const { status, user, logout } = useAuth()
  const navigate = useNavigate()

  function closeNav() {
    setMobileNavOpen(false)
    setOpenMenu(null)
  }

  async function onSignOut() {
    await logout()
    closeNav()
    navigate('/')
  }

  const authenticated = status === 'authenticated' && Boolean(user)
  // admin implies reviewer (RequireAuth applies the same rule to the /review route).
  const canReview =
    authenticated && (user?.role === 'reviewer' || user?.role === 'admin')

  function navLink(to: string, label: string, key = to) {
    return (
      <NavLink
        key={key}
        to={to}
        className="usa-nav__link"
        onClick={closeNav}
      >
        <span>{label}</span>
      </NavLink>
    )
  }

  function navGroup(group: NavGroup) {
    const items = group.items.map((leaf) => navLink(leaf.to, leaf.label))
    const isOpen = openMenu === group.menuId
    return (
      <Fragment key={group.menuId}>
        <NavDropDownButton
          menuId={group.menuId}
          isOpen={isOpen}
          label={group.label}
          onToggle={() =>
            setOpenMenu((cur) => (cur === group.menuId ? null : group.menuId))
          }
        />
        <Menu id={group.menuId} items={items} isOpen={isOpen} />
      </Fragment>
    )
  }

  const navItems: ReactNode[] = [
    navLink('/search', 'Search'),
    navGroup(EXPLORE),
  ]

  if (authenticated) {
    navItems.push(navGroup(WORKSPACES))
    navItems.push(navLink('/ingest', 'Submit a paper'))
    if (canReview) navItems.push(navLink('/review', 'Review'))
    navItems.push(navLink('/account', 'Account'))
  }

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
      navLink('/login', 'Sign in', 'signin')
    ),
  )

  return (
    <>
      <a className="usa-skipnav" href="#main-content">
        Skip to main content
      </a>

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
