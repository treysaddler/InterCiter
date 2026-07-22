import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, api, auth as authApi } from '../api/client'
import type { CurrentUser } from '../api/types'

type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

interface AuthState {
  user: CurrentUser | null
  status: AuthStatus
  login: (apiToken: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthCtx = createContext<AuthState | null>(null)

/**
 * Session-cookie auth (docs/ui-design.md §11). On mount we probe `/users/me`:
 * a 401 simply means anonymous (reads stay open). login/logout go through the
 * BFF endpoints; the raw token is never stored client-side.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<CurrentUser>('/users/me')
      setUser(me)
      setStatus('authenticated')
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) {
        // Unexpected error still resolves to anonymous, but surfacing it is fine.
        // eslint-disable-next-line no-console
        console.error('auth probe failed', e)
      }
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(
    async (apiToken: string) => {
      await authApi.login(apiToken)
      await refresh()
    },
    [refresh],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  return (
    <AuthCtx.Provider value={{ user, status, login, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
