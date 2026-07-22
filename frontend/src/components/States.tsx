import type { ReactNode } from 'react'

/** Loading / error / empty states as designed states, not bare spinners (US-5.3). */

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="margin-top-3 text-base" role="status">
      {label}
    </p>
  )
}

export function ErrorAlert({ message }: { message: string }) {
  return (
    <div className="usa-alert usa-alert--error margin-top-3" role="alert">
      <div className="usa-alert__body">
        <p className="usa-alert__text">{message}</p>
      </div>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="margin-top-3 text-base">{children}</p>
}
