import { useEffect, useRef, useState } from 'react'
import { ApiRequestError, type SourceView } from '../api/client'
import { sameVersion } from '../review/reviewState'
import { getHandoff, type HandoffView } from './api'

export function useReviewHandoff({ saved, onChanged, onUnavailable }: {
  saved: SourceView | null
  onChanged: () => void
  onUnavailable: (message: string) => void
}) {
  const [value, setValue] = useState<HandoffView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const latest = useRef({ saved, onChanged, onUnavailable })
  useEffect(() => { latest.current = { saved, onChanged, onUnavailable } })
  const key = saved ? `${saved.version.document_id}.${saved.version.source_revision_id}.${saved.version.decision_version}.${saved.version.settings_version}.${saved.status}` : ''
  useEffect(() => {
    if (!key) return
    const controller = new AbortController()
    let running = false
    async function refresh() {
      const current = latest.current
      if (!current.saved || running) return
      running = true
      try {
        const next = await getHandoff(current.saved.version.document_id, controller.signal)
        if (controller.signal.aborted) return
        setValue(next); setError(null)
        if (!sameVersion(next.version, current.saved.version)) current.onChanged()
      } catch (cause) {
        if (controller.signal.aborted) return
        const message = cause instanceof Error ? cause.message : 'Review handoff could not be checked.'
        setValue(null); setError(message)
        if (cause instanceof ApiRequestError && [401, 404, 410].includes(cause.status)) current.onUnavailable(message)
      } finally { running = false }
    }
    void refresh()
    const visible = () => { if (document.visibilityState === 'visible') void refresh() }
    const timer = window.setInterval(visible, 10_000)
    document.addEventListener('visibilitychange', visible)
    window.addEventListener('focus', visible)
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', visible); window.removeEventListener('focus', visible) }
  }, [key, attempt])
  const current = saved && value && sameVersion(value.version, saved.version) ? value : null
  return { value: current, error, retry: () => setAttempt(attempt + 1),
    exportApproved: Boolean(current && (!current.require_approval || (current.reviewer_active && current.approved_at))) }
}
