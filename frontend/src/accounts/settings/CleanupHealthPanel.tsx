import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'
import { getCleanupHealth, type CleanupHealthView } from '../../api/client'
import { InlineNotice } from '../../ui/WorkspaceControls'

function ago(value: string, checked: string) {
  const seconds = Math.max(0, Math.floor((Date.parse(checked) - Date.parse(value)) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export function CleanupHealthPanel({ workspaceId }: { workspaceId: string }) {
  const [health, setHealth] = useState<CleanupHealthView | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getCleanupHealth(workspaceId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setHealth(value) })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Cleanup health could not be checked.')
      })
      .finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => controller.abort()
  }, [workspaceId, attempt])
  const StatusIcon = health?.overdue ? AlertTriangle : CheckCircle2
  return (
    <section className="cleanup-health" aria-labelledby="cleanup-health-heading" aria-busy={pending}>
      <div className="cleanup-health-heading">
        <div>
          <h3 id="cleanup-health-heading">Content cleanup</h3>
          <p>Expired and deleted reviews are inaccessible while stored content awaits removal.</p>
        </div>
        <button type="button" className="quiet-button" disabled={pending} onClick={() => {
          setPending(true); setError(null); setAttempt((value) => value + 1)
        }}>
          <RefreshCw size={14} aria-hidden="true" /> {pending ? 'Checking…' : 'Check again'}
        </button>
      </div>
      {error && <InlineNotice error>{error}</InlineNotice>}
      {!health && pending && <p role="status">Checking cleanup health…</p>}
      {health && <div className="cleanup-health-details" role="status">
        <div className="cleanup-health-status" data-overdue={health.overdue}>
          <StatusIcon size={20} aria-hidden="true" />
          <div>
            <strong>{health.overdue ? 'Cleanup is overdue' : 'Cleanup is up to date'}</strong>
            <p>{health.last_success_at
              ? <>Cleanup last completed <time dateTime={health.last_success_at}>{ago(health.last_success_at, health.checked_at)}</time>.</>
              : 'No completed cleanup has been recorded yet.'}</p>
            {health.last_failure_at && <p>A cleanup attempt failed <time dateTime={health.last_failure_at}>{ago(health.last_failure_at, health.checked_at)}</time>.</p>}
            {health.overdue && <p>Ask your service operator to check the scheduled cleanup.</p>}
          </div>
        </div>
        <p className="cleanup-health-awaiting"><strong>{health.documents_awaiting_purge}</strong>
          <span>review{health.documents_awaiting_purge === 1 ? '' : 's'} awaiting content removal</span>
        </p>
      </div>}
    </section>
  )
}
