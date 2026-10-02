import { useSyncExternalStore } from 'react'
import { rememberReviewWorkspace } from './reviewWorkspace'

const EVENT = 'openanonymi:resume-review'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const key = (userId: string, workspaceId: string) => `openanonymi.last-review.${userId}.${workspaceId}`

export function lastReview(userId: string, workspaceId: string): string | null {
  try {
    const value = localStorage.getItem(key(userId, workspaceId))
    return value && uuid.test(value) ? value : null
  } catch { return null }
}

export function rememberReview(userId: string, workspaceId: string, documentId: string) {
  if (!uuid.test(documentId)) return
  rememberReviewWorkspace(userId, workspaceId)
  try { localStorage.setItem(key(userId, workspaceId), documentId) } catch { /* Optional metadata. */ }
  window.dispatchEvent(new Event(EVENT))
}

export function forgetReview(userId: string, workspaceId: string, documentId: string) {
  if (lastReview(userId, workspaceId) !== documentId) return
  try { localStorage.removeItem(key(userId, workspaceId)) } catch { /* No content is retained. */ }
  window.dispatchEvent(new Event(EVENT))
}

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback)
  window.addEventListener('storage', callback)
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', callback) }
}

export function useLastReview(userId: string, workspaceId: string) {
  return useSyncExternalStore(subscribe, () => lastReview(userId, workspaceId), () => null)
}
