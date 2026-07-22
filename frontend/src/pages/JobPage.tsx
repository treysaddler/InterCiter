import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { JobView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'

const TERMINAL = new Set(['succeeded', 'failed'])

/**
 * Job status (US-2.3). Polls GET /v1/jobs/:jobId until the job reaches a terminal
 * state, then links to the extraction run and the paper (or shows the failure).
 */
export default function JobPage() {
  const { jobId = '' } = useParams()
  const [job, setJob] = useState<JobView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const j = await api.get<JobView>(`/jobs/${jobId}`)
        if (!active) return
        setJob(j)
        if (!TERMINAL.has(j.status)) {
          timer = setTimeout(poll, 1000)
        }
      } catch (e) {
        if (active) setError(e instanceof ApiError ? e.message : String(e))
      }
    }

    void poll()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [jobId])

  const workId = job?.result?.work_id as string | undefined
  const availability = job?.result?.availability_state as string | undefined
  const pending = job != null && !TERMINAL.has(job.status)

  return (
    <>
      <PageHeading>Job</PageHeading>
      {error && <ErrorAlert message={error} />}
      {!job && !error && <Loading label="Fetching job…" />}

      {job && (
        <>
          <p className="margin-bottom-1">
            <span className="usa-tag bg-base-lighter text-ink">{job.status}</span>{' '}
            <span className="text-base">{job.job_type}</span>
          </p>
          {pending && <Loading label="Working… polling for completion." />}

          {job.status === 'succeeded' && (
            <div className="usa-alert usa-alert--success margin-top-2" role="status">
              <div className="usa-alert__body">
                <h2 className="usa-alert__heading">Ingested</h2>
                <p className="usa-alert__text">
                  {workId ? (
                    <>
                      <Link to={`/papers/${workId}`}>View the paper →</Link>
                      {availability && <> · {availability}</>}
                    </>
                  ) : (
                    'Completed.'
                  )}
                </p>
                {job.extraction_run_id && (
                  <p className="usa-alert__text">
                    <Link to={`/runs/${job.extraction_run_id}`}>
                      View extraction run →
                    </Link>
                  </p>
                )}
              </div>
            </div>
          )}

          {job.status === 'failed' && (
            <ErrorAlert message={job.error ?? 'The job failed.'} />
          )}
        </>
      )}
    </>
  )
}
