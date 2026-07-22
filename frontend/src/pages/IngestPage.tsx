import { useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { JobView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { ErrorAlert } from '../components/States'

type Mode = 'doi' | 'pmid' | 'xml'

const MANIFESTATIONS = ['preprint', 'published', 'correction', 'retraction_notice']

/**
 * Submit a paper (US-2.1–2.2). POST /v1/papers with a stable idempotency key so a
 * retry never double-ingests. DOI/PMID trigger a server-side fetch; pasting or
 * uploading open-access JATS XML is the offline path.
 */
export default function IngestPage() {
  const navigate = useNavigate()
  // Stable for the life of the form: retrying the same submission reuses the key.
  const idempotencyKey = useMemo(() => crypto.randomUUID(), [])

  const [mode, setMode] = useState<Mode>('doi')
  const [doi, setDoi] = useState('')
  const [pmid, setPmid] = useState('')
  const [xml, setXml] = useState('')
  const [manifestation, setManifestation] = useState('published')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) setXml(await file.text())
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const body: Record<string, unknown> = {
      manifestation,
      idempotency_key: idempotencyKey,
    }
    if (mode === 'doi') body.doi = doi.trim()
    else if (mode === 'pmid') body.pmid = pmid.trim()
    else body.xml = xml
    try {
      const job = await api.post<JobView>('/papers', body)
      navigate(`/jobs/${job.job_id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Submission failed.')
      setBusy(false)
    }
  }

  const ready =
    (mode === 'doi' && doi.trim()) ||
    (mode === 'pmid' && pmid.trim()) ||
    (mode === 'xml' && xml.trim())

  return (
    <div className="grid-row">
      <div className="tablet:grid-col-8">
        <PageHeading>Submit a paper</PageHeading>
        {error && <ErrorAlert message={error} />}

        <form className="usa-form usa-form--large" onSubmit={onSubmit}>
          <fieldset className="usa-fieldset">
            <legend className="usa-legend">Identify the paper by</legend>
            {(['doi', 'pmid', 'xml'] as Mode[]).map((m) => (
              <div className="usa-radio" key={m}>
                <input
                  className="usa-radio__input"
                  id={`mode-${m}`}
                  type="radio"
                  name="mode"
                  checked={mode === m}
                  onChange={() => setMode(m)}
                />
                <label className="usa-radio__label" htmlFor={`mode-${m}`}>
                  {m === 'doi' ? 'DOI' : m === 'pmid' ? 'PMID' : 'Open-access JATS XML'}
                </label>
              </div>
            ))}
          </fieldset>

          {mode === 'doi' && (
            <>
              <label className="usa-label" htmlFor="doi">
                DOI
              </label>
              <input
                className="usa-input"
                id="doi"
                value={doi}
                onChange={(e) => setDoi(e.target.value)}
                placeholder="10.1000/example"
              />
            </>
          )}

          {mode === 'pmid' && (
            <>
              <label className="usa-label" htmlFor="pmid">
                PMID
              </label>
              <input
                className="usa-input"
                id="pmid"
                value={pmid}
                onChange={(e) => setPmid(e.target.value)}
                placeholder="12345678"
              />
            </>
          )}

          {mode === 'xml' && (
            <>
              <label className="usa-label" htmlFor="xml-file">
                Upload JATS XML
              </label>
              <input
                className="usa-file-input"
                id="xml-file"
                type="file"
                accept=".xml,text/xml,application/xml"
                onChange={onFile}
              />
              <label className="usa-label" htmlFor="xml-text">
                …or paste it
              </label>
              <textarea
                className="usa-textarea"
                id="xml-text"
                rows={8}
                value={xml}
                onChange={(e) => setXml(e.target.value)}
              />
            </>
          )}

          <label className="usa-label" htmlFor="manifestation">
            Manifestation
          </label>
          <select
            className="usa-select"
            id="manifestation"
            value={manifestation}
            onChange={(e) => setManifestation(e.target.value)}
          >
            {MANIFESTATIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          <p className="font-body-3xs text-base margin-bottom-0">
            Idempotency key: <code>{idempotencyKey}</code>
          </p>
          <button className="usa-button margin-top-2" type="submit" disabled={busy || !ready}>
            {busy ? 'Submitting…' : 'Submit'}
          </button>
        </form>
      </div>
    </div>
  )
}
