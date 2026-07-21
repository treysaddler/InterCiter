import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * SPA route-change focus management (docs/ui-design.md §5, US-5.1).
 *
 * On every navigation, move focus to the page heading (or the main region) so
 * screen-reader and keyboard users are placed at the top of the new content
 * instead of being stranded where the old link was.
 */
export default function PageFocus() {
  const { pathname } = useLocation()

  useEffect(() => {
    const target =
      document.getElementById('page-heading') ?? document.getElementById('main-content')
    target?.focus()
  }, [pathname])

  return null
}
