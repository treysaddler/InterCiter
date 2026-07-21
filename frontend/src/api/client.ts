/**
 * Thin fetch wrapper for the InterCiter `/v1` API.
 *
 * Auth model (docs/ui-design.md §11): the browser never holds the raw bearer
 * token. Requests are same-origin and carry the BFF session cookie via
 * `credentials: 'include'`. A generated OpenAPI client will replace the hand
 * typing in `types.ts` later; this wrapper stays as the transport.
 */

const BASE = '/v1'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
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
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  health: () => fetch('/health').then((r) => r.json() as Promise<{ status: string }>),
}
