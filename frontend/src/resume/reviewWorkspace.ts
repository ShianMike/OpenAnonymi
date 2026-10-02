import { useSyncExternalStore } from 'react'

const event = 'openanonymi:review-workspace'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const key = (userId: string) => `openanonymi.review-workspace.${userId}`

export function lastReviewWorkspace(userId: string): string | null {
  try {
    const value = localStorage.getItem(key(userId))
    return value && uuid.test(value) ? value : null
  } catch { return null }
}

export function rememberReviewWorkspace(userId: string, workspaceId: string) {
  if (!uuid.test(workspaceId) || lastReviewWorkspace(userId) === workspaceId) return
  try { localStorage.setItem(key(userId), workspaceId) } catch { /* The URL still preserves workspace selection. */ }
  window.dispatchEvent(new Event(event))
}

function subscribe(callback: () => void) {
  window.addEventListener(event, callback)
  window.addEventListener('storage', callback)
  return () => { window.removeEventListener(event, callback); window.removeEventListener('storage', callback) }
}

export function useReviewWorkspace(userId: string) {
  return useSyncExternalStore(subscribe, () => lastReviewWorkspace(userId), () => null)
}
