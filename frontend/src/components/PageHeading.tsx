import type { ReactNode } from 'react'

/**
 * Standard page heading. `id`/`tabIndex` let PageFocus move focus here on
 * navigation without adding it to the tab order permanently.
 */
export default function PageHeading({ children }: { children: ReactNode }) {
  return (
    <h1 id="page-heading" tabIndex={-1} className="margin-top-4">
      {children}
    </h1>
  )
}
