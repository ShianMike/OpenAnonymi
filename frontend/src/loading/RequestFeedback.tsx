import { useEffect, useState, useSyncExternalStore } from 'react'
import { requestSnapshot, subscribeRequests } from '../api/requestActivity'
import { LoadingState } from './LoadingState'
import { useForegroundLoading } from './foregroundLoading'

/** A quiet, nonblocking signal for real requests. Fast requests never display it. */
export function RequestFeedback() {
  const requests = useSyncExternalStore(subscribeRequests, requestSnapshot)
  const foreground = useForegroundLoading()
  const first = requests[0]
  const [visibleId, setVisibleId] = useState<number | null>(null)
  useEffect(() => {
    if (!first) return
    const timer = window.setTimeout(() => setVisibleId(first.id), Math.max(0, 600 - (Date.now() - first.startedAt)))
    return () => clearTimeout(timer)
  }, [first])
  if (!first || visibleId !== first.id || foreground) return null
  const labels = [...new Set(requests.map(item => item.label))]
  return <aside className="request-feedback" aria-label="Work in progress">
    <LoadingState key={first.id} label={`${first.label}…`} compact />
    {labels.length > 1 && <span className="request-feedback-count">Also: {labels.slice(1).join(' · ')}</span>}
  </aside>
}
