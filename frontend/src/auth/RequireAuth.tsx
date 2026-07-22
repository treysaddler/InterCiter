import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from './AuthContext'

/**
 * Gate a route on authentication and (optionally) role. `admin` always satisfies.
 * While the auth probe is in flight we render nothing to avoid a flash of the
 * login redirect.
 */
export default function RequireAuth({
  children,
  roles,
}: {
  children: ReactNode
  roles?: string[]
}) {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') return null
  if (status === 'anonymous' || !user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (roles && user.role !== 'admin' && !roles.includes(user.role)) {
    return (
      <div className="usa-alert usa-alert--error margin-top-4" role="alert">
        <div className="usa-alert__body">
          <h2 className="usa-alert__heading">Not authorized</h2>
          <p className="usa-alert__text">
            This area requires one of: {roles.join(', ')}.
          </p>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
