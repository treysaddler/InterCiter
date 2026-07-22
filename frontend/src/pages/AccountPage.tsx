import { useState, type FormEvent } from 'react'

import { ApiError, api } from '../api/client'
import type { UserView, UserWithToken } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

const ROLES = ['user', 'reviewer', 'admin']

/**
 * Account (US-4.1–4.2). Any authenticated user sees their identity; admins get the
 * manual account-management surface (list, create, role, activation, token
 * rotation). Raw tokens are shown exactly once.
 */
export default function AccountPage() {
  const { user } = useAuth()
  return (
    <>
      <PageHeading>Account</PageHeading>
      {user && (
        <dl className="font-body-sm">
          <dt className="text-bold">Name</dt>
          <dd className="margin-left-0">{user.display_name}</dd>
          <dt className="text-bold">Role</dt>
          <dd className="margin-left-0">{user.role}</dd>
          <dt className="text-bold">User ID</dt>
          <dd className="margin-left-0 font-mono-3xs">{user.user_id}</dd>
        </dl>
      )}
      {user?.role === 'admin' && <UserAdmin />}
    </>
  )
}

function TokenReveal({ user }: { user: UserWithToken }) {
  return (
    <div className="usa-alert usa-alert--success margin-top-2" role="status">
      <div className="usa-alert__body">
        <h3 className="usa-alert__heading">
          Token for {user.display_name} — shown once
        </h3>
        <p className="usa-alert__text">
          <code>{user.api_token}</code>
        </p>
        <button
          type="button"
          className="usa-button usa-button--outline"
          onClick={() => void navigator.clipboard?.writeText(user.api_token)}
        >
          Copy
        </button>
        <p className="usa-alert__text font-body-3xs">
          Store it now — only its hash is kept; it cannot be shown again.
        </p>
      </div>
    </div>
  )
}

function UserAdmin() {
  const { data, error, loading, reload } = useApi<UserView[]>(
    () => api.get<UserView[]>('/users'),
    [],
  )
  const [actionError, setActionError] = useState<string | null>(null)
  const [revealed, setRevealed] = useState<UserWithToken | null>(null)

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setActionError(null)
    try {
      return await fn()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Action failed.')
      return undefined
    }
  }

  async function create(displayName: string, role: string) {
    const created = await run(() =>
      api.post<UserWithToken>('/users', { display_name: displayName, role }),
    )
    if (created) {
      setRevealed(created)
      reload()
    }
  }

  async function setRole(id: string, role: string) {
    if (await run(() => api.patch<UserView>(`/users/${id}`, { role }))) reload()
  }

  async function setActive(id: string, isActive: boolean) {
    if (await run(() => api.patch<UserView>(`/users/${id}`, { is_active: isActive })))
      reload()
  }

  async function rotate(id: string) {
    const rotated = await run(() =>
      api.post<UserWithToken>(`/users/${id}/rotate-token`),
    )
    if (rotated) setRevealed(rotated)
  }

  return (
    <section className="margin-top-4">
      <h2>Manage users</h2>
      {actionError && <ErrorAlert message={actionError} />}
      {revealed && <TokenReveal user={revealed} />}

      <CreateUserForm onCreate={create} />

      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}
      {data && (
        <table className="usa-table usa-table--borderless width-full margin-top-3">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((u) => (
              <tr key={u.user_id}>
                <td>{u.display_name}</td>
                <td>
                  <select
                    className="usa-select"
                    aria-label={`Role for ${u.display_name}`}
                    value={u.role}
                    onChange={(e) => void setRole(u.user_id, e.target.value)}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <span
                    className={`usa-tag ${u.is_active ? 'bg-mint text-ink' : 'bg-base-lighter text-ink'}`}
                  >
                    {u.is_active ? 'active' : 'inactive'}
                  </span>
                </td>
                <td>
                  <button
                    type="button"
                    className="usa-button usa-button--outline usa-button--small"
                    onClick={() => void setActive(u.user_id, !u.is_active)}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button
                    type="button"
                    className="usa-button usa-button--outline usa-button--small"
                    onClick={() => void rotate(u.user_id)}
                  >
                    Rotate token
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function CreateUserForm({
  onCreate,
}: {
  onCreate: (name: string, role: string) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [role, setRole] = useState('user')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    await onCreate(trimmed, role)
    setName('')
    setRole('user')
  }

  return (
    <form className="usa-form usa-form--large margin-top-2" onSubmit={onSubmit}>
      <h3>Create a user</h3>
      <label className="usa-label" htmlFor="new-name">
        Display name
      </label>
      <input
        className="usa-input"
        id="new-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <label className="usa-label" htmlFor="new-role">
        Role
      </label>
      <select
        className="usa-select"
        id="new-role"
        value={role}
        onChange={(e) => setRole(e.target.value)}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <button className="usa-button margin-top-2" type="submit" disabled={!name.trim()}>
        Create
      </button>
    </form>
  )
}
