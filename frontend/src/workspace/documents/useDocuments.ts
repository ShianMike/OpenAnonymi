import { useEffect, useState } from 'react'
import { getWorkspaceDocuments, type DocumentIndexView } from '../../api/client'
import { availableReview } from '../../resume/reviewQueue'
import { forgetReview, lastReview } from '../../resume/lastReview'

type Data = { key: string } & (
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: DocumentIndexView[]; unavailable: boolean; checkedAt: number; refreshing: boolean }
)

/** Recheck on return; failed access checks never leave stale titles actionable. */
export function useDocuments(userId: string, workspaceId: string, busy: boolean) {
  const key = `${userId}.${workspaceId}`
  const [data, setData] = useState<Data>({ key, kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspaceId || busy) return
    const controller = new AbortController()
    let running = false
    async function load() {
      if (running || controller.signal.aborted) return
      running = true
      setData(current => current.key === key && current.kind === 'ready'
        ? { ...current, refreshing: true } : { key, kind: 'loading' })
      try {
        const items = await getWorkspaceDocuments(workspaceId, controller.signal)
        if (controller.signal.aborted) return
        const checkedAt = Date.now()
        const previous = lastReview(userId, workspaceId)
        const unavailable = !!previous && !items.some(item => item.id === previous && availableReview(item, checkedAt))
        if (previous && unavailable) forgetReview(userId, workspaceId, previous)
        setData({ key, kind: 'ready', items, unavailable, checkedAt, refreshing: false })
      } catch (cause) {
        if (!controller.signal.aborted) setData({ key, kind: 'error',
          message: cause instanceof Error ? cause.message : 'Documents could not be loaded.' })
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
  }, [key, userId, workspaceId, attempt, busy])
  function updateItems(change: (items: DocumentIndexView[]) => DocumentIndexView[]) {
    setData(current => current.key === key && current.kind === 'ready' ? { ...current, items: change(current.items) } : current)
  }
  return { data: data.key === key ? data : { key, kind: 'loading' as const }, updateItems,
    retry: () => setAttempt(value => value + 1) }
}
