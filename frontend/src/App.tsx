import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'

import AppShell from './components/AppShell'
import RequireAuth from './auth/RequireAuth'
import { Loading } from './components/States'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
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

// The graph view pulls in Cytoscape (a large canvas library) that no other screen
// needs, so it is code-split and only fetched when a user opens /graph.
const GraphPage = lazy(() => import('./pages/GraphPage'))

/**
 * Route map mirrors the information architecture in docs/ui-design.md §5.
 * Reads are open; write-oriented areas are gated by RequireAuth.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="papers" element={<PapersPage />} />
        <Route path="papers/:workId" element={<PaperDetailPage />} />
        <Route path="papers/:workId/claims/:claimId" element={<ClaimDetailPage />} />
        {/* Standalone claim route for links from relations/traces. */}
        <Route path="claims/:claimId" element={<ClaimDetailPage />} />
        <Route
          path="graph"
          element={
            <Suspense fallback={<Loading label="Loading graph…" />}>
              <GraphPage />
            </Suspense>
          }
        />
        <Route
          path="graph/papers/:workId"
          element={
            <Suspense fallback={<Loading label="Loading graph…" />}>
              <GraphPage />
            </Suspense>
          }
        />
        <Route
          path="ingest"
          element={
            <RequireAuth>
              <IngestPage />
            </RequireAuth>
          }
        />
        <Route path="jobs/:jobId" element={<JobPage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route
          path="review"
          element={
            <RequireAuth roles={['reviewer']}>
              <ReviewPage />
            </RequireAuth>
          }
        />
        <Route path="clusters/:clusterId" element={<ClusterPage />} />
        <Route
          path="account"
          element={
            <RequireAuth>
              <AccountPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
