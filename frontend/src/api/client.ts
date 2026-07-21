/**
 * Thin fetch wrapper for the InterCiter `/v1` API.
 *
 * Auth model (docs/ui-design.md §11): the browser never holds the raw bearer
 * token. Requests are same-origin and carry the BFF session cookie via
 * `credentials: 'include'`. Unsafe methods echo the CSRF token (read from the
 * readable `interciter_csrf` cookie) in the `X-CSRF-Token` header. A generated
 * OpenAPI client will replace the hand typing in `types.ts` later; this wrapper
 * stays as the transport.
 */

import type { SessionInfo } from './types'

const BASE = '/v1'
const CSRF_COOKIE = 'interciter_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  if (UNSAFE.has(method)) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) headers[CSRF_HEADER] = csrf
  }

  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers,
    ...init,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  health: () => fetch('/health').then((r) => r.json() as Promise<{ status: string }>),
}

/**
 * Session (BFF) helpers. `login` exchanges a raw token — sent once, never stored —
 * for the HttpOnly session cookie; the SPA keeps only the returned CSRF token in
 * memory (also mirrored to the readable cookie by the server).
 */
export const auth = {
  login: (apiToken: string) =>
    api.post<SessionInfo>('/auth/login', { api_token: apiToken }),
  logout: () => api.post<void>('/auth/logout'),
  csrf: () => api.get<SessionInfo>('/auth/csrf'),
}

