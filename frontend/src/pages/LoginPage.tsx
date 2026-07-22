import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import PageHeading from '../components/PageHeading'
import { ErrorAlert } from '../components/States'
import { useAuth } from '../auth/AuthContext'

/**
 * Login (US-4.1). The API token is pasted once, POSTed to the BFF, and never
 * stored client-side (docs/ui-design.md §11). On success the server sets the
 * session cookie and we return to the page the user came from.
 */
export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(token.trim())
      navigate(from, { replace: true })
    } catch {
      setError('Sign-in failed. Check the token, or your account may be inactive.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid-row">
      <div className="tablet:grid-col-6">
        <PageHeading>Sign in</PageHeading>
        <p>
          Paste your InterCiter API token. It is sent once to establish a secure
          session and is never stored in your browser.
        </p>

        {error && <ErrorAlert message={error} />}

        <form className="usa-form" onSubmit={onSubmit}>
          <label className="usa-label" htmlFor="api-token">
            API token
          </label>
          <input
            className="usa-input"
            id="api-token"
            name="api-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
          />
          <button className="usa-button margin-top-2" type="submit" disabled={busy || !token.trim()}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
