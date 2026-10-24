import { useEffect, useState } from 'react'
import { getDocumentHistory, type DocumentHistoryView } from '../../api/client'
import { historyAvailable } from './historyPresentation'

type Data = { key: string } & (
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; value: DocumentHistoryView; checkedAt: string }
)

export function useHistory(workspaceId: string, documentId: string) {
  const key = `${workspaceId}.${documentId}`
  const [data, setData] = useState<Data>({ key, kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspaceId || !documentId) return
    let request: AbortController | null = null
    let expiry: ReturnType<typeof setTimeout> | undefined
    async function load() {
      request?.abort()
      clearTimeout(expiry)
      const controller = new AbortController()
      request = controller
      setData({ key, kind: 'loading' })
      try {
        const value = await getDocumentHistory(workspaceId, documentId, controller.signal)
        if (controller.signal.aborted) return
        const now = Date.now()
        setData({ key, kind: 'ready', value, checkedAt: new Date(now).toISOString() })
        // Discard compared source text at its retention boundary, including long retentions.
        if (historyAvailable(value, now)) expiry = setTimeout(() => void load(), Math.min(Date.parse(value.expires_at) - now, 2_147_483_647))
      } catch (cause) {
        if (!controller.signal.aborted) setData({ key, kind: 'error', message: cause instanceof Error ? cause.message : 'History could not be loaded.' })
      }
    }
    void load()
    const focus = () => { if (document.visibilityState === 'visible') void load() }
    const visibility = () => {
      if (document.visibilityState === 'visible') void load()
      else { request?.abort(); clearTimeout(expiry); setData({ key, kind: 'loading' }) }
    }
    window.addEventListener('focus', focus)
    document.addEventListener('visibilitychange', visibility)
    return () => { request?.abort(); clearTimeout(expiry); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', visibility) }
  }, [key, workspaceId, documentId, attempt])
  return { data: data.key === key ? data : { key, kind: 'loading' as const }, retry: () => setAttempt(value => value + 1) }
}
