import { Link } from 'react-router-dom'

import PageHeading from '../components/PageHeading'

export default function NotFoundPage() {
  return (
    <>
      <PageHeading>Page not found</PageHeading>
      <p>
        The page you requested does not exist. <Link to="/">Return home</Link>.
      </p>
    </>
  )
}
