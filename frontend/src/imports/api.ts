import { trackedRequest } from '../api/requestActivity'
import { requireSuccess } from '../api/client'
import type { components } from '../api/schema'

export type ImportPreview = components['schemas']['ImportPreview']

export async function importPreview(workspace: string, file: File, csrf: string): Promise<ImportPreview> {
  const form = new FormData()
  form.set('workspace_id', workspace)
  form.set('file', file)
  return trackedRequest('/api/v1/documents/import-preview', { method: 'POST', body: form,
    credentials: 'same-origin', cache: 'no-store', headers: { 'X-CSRF-Token': csrf } }, async (response) => {
    await requireSuccess(response)
    return response.json() as Promise<ImportPreview>
  })
}
