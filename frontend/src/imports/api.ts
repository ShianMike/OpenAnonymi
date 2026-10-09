import { API_CREDENTIALS, apiUrl } from '../api/base'
import { trackedRequest } from '../api/requestActivity'
import { requireSuccess } from '../api/client'
import type { components } from '../api/schema'
import type { CsvDelimiter } from '../api/client'

export type ImportPreview = components['schemas']['ImportPreview']

export async function importPreview(workspace: string, file: File, csrf: string, delimiter: CsvDelimiter | 'auto' = 'auto', header: 'auto' | 'true' | 'false' = 'auto'): Promise<ImportPreview> {
  const form = new FormData()
  form.set('workspace_id', workspace)
  form.set('file', file)
  form.set('csv_delimiter', delimiter)
  form.set('csv_header', header)
  return trackedRequest(apiUrl('/documents/import-preview'), { method: 'POST', body: form,
    credentials: API_CREDENTIALS, cache: 'no-store', headers: { 'X-CSRF-Token': csrf } }, async (response) => {
    await requireSuccess(response)
    return response.json() as Promise<ImportPreview>
  })
}
