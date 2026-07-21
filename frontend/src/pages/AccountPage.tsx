import PageHeading from '../components/PageHeading'

/**
 * Account (US-4.1–4.2). Consumes: GET /v1/users/me; admin-only POST /v1/users
 * (raw token shown exactly once). Auth is the BFF session cookie (§11).
 */
export default function AccountPage() {
  return (
    <>
      <PageHeading>Account</PageHeading>
      <p>
        Current user from <code>GET /v1/users/me</code>. Admins can create users;
        the raw token is shown exactly once on creation.
      </p>
    </>
  )
}
