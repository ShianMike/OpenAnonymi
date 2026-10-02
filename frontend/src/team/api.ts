import { trackedRequest } from '../api/requestActivity'
import { get, requireSuccess, sendJson, type VersionRef } from '../api/client'
import type { components } from '../api/schema'

export type HandoffView = components['schemas']['HandoffView']
export type TeammateView = components['schemas']['TeammateView']
export type CommentView = components['schemas']['CommentView']
export const getHandoff = (document: string, signal?: AbortSignal) => get<HandoffView>(`/documents/${document}/handoff`, signal)
export const getTeammates = (document: string, signal?: AbortSignal) => get<TeammateView[]>(`/documents/${document}/teammates`, signal)
export const saveHandoff = (document: string, expected: VersionRef, reviewer: string | null, require: boolean, csrf: string) =>
  sendJson<HandoffView>('PUT', `/documents/${document}/handoff`, { expected, reviewer_id: reviewer, require_approval: require }, csrf)
export const approveReview = (document: string, expected: VersionRef, csrf: string) =>
  sendJson<HandoffView>('POST', `/documents/${document}/approval`, { expected, confirmed_preview: true }, csrf)
export const getComments = (document: string, finding: string, signal?: AbortSignal) => get<CommentView[]>(`/documents/${document}/findings/${finding}/comments`, signal)
export const postComment = (document: string, finding: string, expected: VersionRef, id: string, text: string, csrf: string) =>
  sendJson<CommentView>('POST', `/documents/${document}/findings/${finding}/comments`, { id, expected, text }, csrf)
export async function removeComment(document: string, comment: string, csrf: string) {
  return trackedRequest(`/api/v1/documents/${document}/comments/${comment}`, { method: 'DELETE',
    credentials: 'same-origin', cache: 'no-store', headers: { 'X-CSRF-Token': csrf } }, async (response) => {
    await requireSuccess(response)
  })
}
