import { Routes, Route } from 'react-router-dom'

import AppShell from './components/AppShell'
import HomePage from './pages/HomePage'
import PapersPage from './pages/PapersPage'
import PaperDetailPage from './pages/PaperDetailPage'
import ClaimDetailPage from './pages/ClaimDetailPage'
import IngestPage from './pages/IngestPage'
import JobPage from './pages/JobPage'
import RunPage from './pages/RunPage'
import ReviewPage from './pages/ReviewPage'
import ClusterPage from './pages/ClusterPage'
import AccountPage from './pages/AccountPage'
import NotFoundPage from './pages/NotFoundPage'

/**
 * Route map mirrors the information architecture in docs/ui-design.md §5.
 * Every screen is a stub today; each names the /v1 endpoints it will consume.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="papers" element={<PapersPage />} />
        <Route path="papers/:workId" element={<PaperDetailPage />} />
        <Route path="papers/:workId/claims/:claimId" element={<ClaimDetailPage />} />
        <Route path="ingest" element={<IngestPage />} />
        <Route path="jobs/:jobId" element={<JobPage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="clusters/:clusterId" element={<ClusterPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
