import { API_CREDENTIALS, apiUrl } from '../api/base'
import { get, requireSuccess, sendJson } from '../api/client'
import { trackedRequest } from '../api/requestActivity'
import type { components } from '../api/schema'

export type BatchView = components['schemas']['BatchView']
export type BatchList = components['schemas']['BatchList']
export type BatchEligibility = components['schemas']['BatchEligibility']
export type CreateBatchRequest = components['schemas']['CreateBatchRequest']
export type BatchDocument = BatchView['documents'][number]
export type OutputMode = 'original' | 'txt'
const path = (id: string) => `/batches/${encodeURIComponent(id)}`

export const getBatches = (workspace: string, signal?: AbortSignal) =>
  get<BatchList>(`/batches?workspace_id=${encodeURIComponent(workspace)}`, signal)
export const createBatch = (body: CreateBatchRequest, csrf: string) =>
  sendJson<BatchView>('POST', '/batches', body, csrf)
export const getBatch = (id: string, signal?: AbortSignal) => get<BatchView>(path(id), signal)
export const getEligibility = (id: string, signal?: AbortSignal) =>
  get<BatchEligibility>(`${path(id)}/outputs/eligibility`, signal)
export const retryScan = (batch: string, document: string, csrf: string) =>
  sendJson<void>('POST', `${path(batch)}/documents/${encodeURIComponent(document)}/retry`, undefined, csrf)

export async function uploadBatchFile(id: string, file: File, csrf: string, signal?: AbortSignal): Promise<void> {
  const form = new FormData()
  form.set('file', file)
  await trackedRequest(apiUrl(`${path(id)}/documents`), {
    method: 'POST', body: form, credentials: API_CREDENTIALS, cache: 'no-store', signal,
    headers: { 'X-CSRF-Token': csrf },
  }, requireSuccess)
}

export async function deleteBatch(id: string, csrf: string): Promise<void> {
  await trackedRequest(apiUrl(path(id)), {
    method: 'DELETE', credentials: API_CREDENTIALS, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify({ confirmed: true }),
  }, requireSuccess)
}

export async function downloadBatch(id: string, mode: OutputMode, csrf: string): Promise<Blob> {
  return trackedRequest(apiUrl(`${path(id)}/outputs`), {
    method: 'POST', credentials: API_CREDENTIALS, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify({ request_id: crypto.randomUUID(), mode }),
  }, async (response) => {
    await requireSuccess(response)
    return response.blob()
  })
}
