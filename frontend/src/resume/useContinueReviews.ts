import { useEffect, useState } from 'react'
import { getWorkspaceDocuments, type DocumentIndexView } from '../api/client'
import { availableReview } from './reviewQueue'
import { forgetReview, lastReview } from './lastReview'

type Data = { key: string } & (
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: DocumentIndexView[]; unavailable: boolean; checkedAt: number; refreshing: boolean }
)

/** Recheck the authorized index on return; never keep actionable stale titles after an error. */
export function useContinueReviews(userId: string, workspaceId: string) {
  const key = `${userId}.${workspaceId}`
  const [data, setData] = useState<Data>({ key, kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    let running = false
    let unavailable = false
    async function load() {
      if (running || controller.signal.aborted) return
      running = true
      setData((current) => current.key === key && current.kind === 'ready'
        ? { ...current, refreshing: true } : { key, kind: 'loading' })
      try {
        const items = await getWorkspaceDocuments(workspaceId, controller.signal)
        if (controller.signal.aborted) return
        const checkedAt = Date.now()
        const previous = lastReview(userId, workspaceId)
        if (previous) {
          unavailable = !items.some((item) => item.id === previous && availableReview(item, checkedAt))
          if (unavailable) forgetReview(userId, workspaceId, previous)
        }
        setData({ key, kind: 'ready', items, unavailable, checkedAt, refreshing: false })
      } catch (cause: unknown) {
        if (!controller.signal.aborted) setData({ key, kind: 'error',
          message: cause instanceof Error ? cause.message : 'Your reviews could not be loaded.' })
      } finally { running = false }
    }
    void load()
    const visible = () => { if (document.visibilityState === 'visible') void load() }
    window.addEventListener('focus', visible)
    document.addEventListener('visibilitychange', visible)
    const timer = window.setInterval(visible, 30_000)
    return () => {
      controller.abort()
      clearInterval(timer)
      window.removeEventListener('focus', visible)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [key, userId, workspaceId, attempt])
  return { data: data.key === key ? data : { key, kind: 'loading' as const },
    retry: () => setAttempt((value) => value + 1) }
}
