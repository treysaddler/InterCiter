import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { CitationStats, ClaimView, PaperView } from '../api/types'
import CitationTallies from '../components/CitationTallies'
import IntegrityBadges from '../components/IntegrityBadges'
import PageHeading from '../components/PageHeading'
import RelatedWork from '../components/RelatedWork'
import { Empty, ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Paper detail (US-1.1). Consumes GET /v1/papers/:id and /v1/papers/:id/claims.
 */
export default function PaperDetailPage() {
  const { workId = '' } = useParams()

  const paper = useApi<PaperView>(() => api.get<PaperView>(`/papers/${workId}`), [workId])
  const claims = useApi<ClaimView[]>(
    () => api.get<ClaimView[]>(`/papers/${workId}/claims`),
    [workId],
  )
  const stats = useApi<CitationStats>(
    () => api.get<CitationStats>(`/papers/${workId}/citation-stats`),
    [workId],
  )

  return (
    <>
      <p className="margin-top-4 margin-bottom-0">
        <Link to="/papers">← All papers</Link>
      </p>
      <PageHeading>{paper.data?.title ?? 'Paper'}</PageHeading>

      {paper.loading && <Loading />}
      {paper.error && <ErrorAlert message={paper.error} />}
      {paper.data?.is_retracted && (
        <div
          className="usa-alert usa-alert--error usa-alert--slim margin-top-2"
          role="alert"
        >
          <div className="usa-alert__body">
            <p className="usa-alert__text">
              This work has been retracted
              {paper.data.integrity_notice
                ? ` (${paper.data.integrity_notice.replaceAll('_', ' ')})`
                : ''}
              . Interpret its citations accordingly.
            </p>
          </div>
        </div>
      )}
      {paper.data && (
        <ul className="usa-list usa-list--unstyled text-base">
          {paper.data.authors.length > 0 && <li>{paper.data.authors.join(', ')}</li>}
          <li>
            {[paper.data.venue, paper.data.year].filter(Boolean).join(' · ') || '—'}
          </li>
          <li>
            {paper.data.doi && <span>DOI {paper.data.doi} </span>}
            {paper.data.pmid && <span>· PMID {paper.data.pmid}</span>}
          </li>
          <li className="margin-top-1">
            <span className="usa-tag bg-base-lighter text-ink">
              {paper.data.availability_state}
            </span>
            <IntegrityBadges
              isRetracted={paper.data.is_retracted}
              integrityNotice={paper.data.integrity_notice}
              className="margin-left-1"
            />
          </li>
          <li className="margin-top-1">
            <Link to={`/graph/papers/${workId}`}>Explore citation network →</Link>
          </li>
          <li className="margin-top-1">
            <Link to={`/papers/${workId}/report`}>View citation report →</Link>
          </li>
        </ul>
      )}

      <h2 className="margin-top-4">How this paper has been cited</h2>
      {stats.loading && <Loading />}
      {stats.error && <ErrorAlert message={stats.error} />}
      {stats.data && <CitationTallies tallies={stats.data.tallies} />}

      <h2 className="margin-top-4">Related work</h2>
      <RelatedWork workId={workId} />

      <h2 className="margin-top-4">Claims</h2>
      {claims.loading && <Loading />}
      {claims.error && <ErrorAlert message={claims.error} />}
      {claims.data && claims.data.length === 0 && <Empty>No claims extracted.</Empty>}
      {claims.data && claims.data.length > 0 && (
        <ul className="usa-list">
          {claims.data.map((c) => (
            <li key={c.claim_id} className="margin-bottom-1">
              <Link to={`/papers/${workId}/claims/${c.claim_id}`}>
                {c.normalized_text}
              </Link>
              {c.evidence.section && (
                <span className="font-body-3xs text-base"> · {c.evidence.section}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
