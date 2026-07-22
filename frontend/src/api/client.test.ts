import { afterEach, beforeEach, vi } from 'vitest'

import { api } from './client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api client CSRF + credentials', () => {
  beforeEach(() => {
    // A readable CSRF cookie as the server would set on login.
    document.cookie = 'interciter_csrf=csrf-abc'
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.cookie = 'interciter_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('sends credentials and NO CSRF header on a GET', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ ok: true }))

    await api.get('/papers')

    const [, init] = fetchMock.mock.calls[0]
    expect(init?.credentials).toBe('include')
    const headers = init?.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBeUndefined()
  })

  it('attaches the X-CSRF-Token header (from cookie) on an unsafe method', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ id: 'job_1' }))

    await api.post('/papers', { doi: '10.1/x' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/v1/papers')
    expect(init?.method).toBe('POST')
    const headers = init?.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('csrf-abc')
    expect(init?.credentials).toBe('include')
  })

  it('throws ApiError with the server detail on a non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'missing or invalid CSRF token' }, 403),
    )

    await expect(api.post('/papers', {})).rejects.toMatchObject({
      status: 403,
      message: 'missing or invalid CSRF token',
    })
  })

  it('returns undefined for a 204 No Content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.del('/auth/logout')).resolves.toBeUndefined()
  })
})
