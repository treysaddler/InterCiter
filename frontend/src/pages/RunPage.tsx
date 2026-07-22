import { useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { ExtractionRunView } from '../api/types'
import PageHeading from '../components/PageHeading'
import { ErrorAlert, Loading } from '../components/States'
import { useApi } from '../hooks/useApi'

/**
 * Extraction-run provenance. Consumes GET /v1/extraction-runs/:runId
 * (model, prompt version, parameters, code revision).
 */
export default function RunPage() {
  const { runId = '' } = useParams()
  const { data, error, loading } = useApi<ExtractionRunView>(
    () => api.get<ExtractionRunView>(`/extraction-runs/${runId}`),
    [runId],
  )

  const rows: [string, string | null | undefined][] = data
    ? [
        ['Model', data.model],
        ['Provider', data.provider],
        ['Model version', data.model_version],
        ['Prompt template', data.prompt_template_version],
        ['Parser version', data.parser_version],
        ['Code revision', data.code_revision],
        ['Timestamp', data.timestamp],
      ]
    : []

  return (
    <>
      <PageHeading>Extraction run</PageHeading>
      {loading && <Loading />}
      {error && <ErrorAlert message={error} />}
      {data && (
        <table className="usa-table usa-table--borderless margin-top-2">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td>{v ?? '—'}</td>
              </tr>
            ))}
            {data.inference_parameters && (
              <tr>
                <th scope="row">Inference parameters</th>
                <td>
                  <code>{JSON.stringify(data.inference_parameters)}</code>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </>
  )
}
