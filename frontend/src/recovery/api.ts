import { trackedRequest } from '../api/requestActivity'
import type { components } from '../api/schema'
import { get, requireSuccess, sendJson } from '../api/client'

export type RecoveryPayload = components['schemas']['RecoveryPayload']
export type RecoveryMetadata = components['schemas']['RecoveryMetadata']
export type RecoveryView = components['schemas']['RecoveryView']

function base(workspaceId: string) {
  return `/workspaces/${encodeURIComponent(workspaceId)}/recovery`
}

export function listRecovery(workspaceId: string, documentId: string | null, signal?: AbortSignal) {
  return get<RecoveryMetadata[]>(base(workspaceId) + (documentId ? `?document_id=${encodeURIComponent(documentId)}` : ''), signal)
}

export function getRecovery(workspaceId: string, id: string, signal?: AbortSignal) {
  return get<RecoveryView>(`${base(workspaceId)}/${encodeURIComponent(id)}`, signal)
}

export function saveRecovery(workspaceId: string, id: string, version: number,
  documentId: string | null, payload: RecoveryPayload, csrf: string) {
  return sendJson<RecoveryMetadata>('PUT', `${base(workspaceId)}/${encodeURIComponent(id)}`, {
    expected_version: version, document_id: documentId, payload,
  }, csrf)
}

export async function deleteRecovery(workspaceId: string, id: string, version: number, csrf: string) {
  return trackedRequest(`/api/v1${base(workspaceId)}/${encodeURIComponent(id)}?expected_version=${version}`, {
    method: 'DELETE', credentials: 'same-origin', cache: 'no-store',
    headers: { 'X-CSRF-Token': csrf },
  }, async (response) => {
    await requireSuccess(response)
  })
}
