import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { getCleanupHealth, type CleanupHealthView } from '../../api/client'
import { InlineNotice, RefreshButton } from '../../ui/WorkspaceControls'
import { LoadingState } from '../../loading/LoadingState'

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

export function CleanupStatus({ health }: { health: CleanupHealthView }) {
  const StatusIcon = health.overdue ? AlertTriangle : CheckCircle2
  return <div role="status"><div className="settings-cleanup-status" data-overdue={health.overdue}><StatusIcon size={18} aria-hidden="true" /><div>
    <strong>{health.overdue ? 'Cleanup needs attention' : health.last_success_at ? 'Cleanup is up to date' : 'No completed cleanup recorded'}</strong>
    <p>{health.last_success_at ? <>Last completed <time dateTime={health.last_success_at} title={new Date(health.last_success_at).toLocaleString()}>{ago(health.last_success_at, health.checked_at)}</time>.</> : 'No completed cleanup has been recorded yet.'}</p>
    {health.last_failure_at && <p>Last recorded failure: <time dateTime={health.last_failure_at} title={new Date(health.last_failure_at).toLocaleString()}>{ago(health.last_failure_at, health.checked_at)}</time>.</p>}
    {health.overdue && <p>Ask your service operator to check scheduled cleanup.</p>}
  </div></div><p className="settings-cleanup-count"><strong>{health.documents_awaiting_purge}</strong> {health.documents_awaiting_purge === 1 ? 'review in this workspace is' : 'reviews in this workspace are'} awaiting content removal.</p></div>
}

export function CleanupHealthPanel({ workspaceId, onRequestFailed }: { workspaceId: string; onRequestFailed: (cause: unknown) => void }) {
  const [health, setHealth] = useState<CleanupHealthView | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getCleanupHealth(workspaceId, controller.signal)
      .then(value => { if (!controller.signal.aborted) setHealth(value) })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Cleanup health could not be checked.'); onRequestFailed(cause) } })
      .finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => controller.abort()
  }, [workspaceId, attempt, onRequestFailed])
  return <section className="settings-section" aria-labelledby="cleanup-health-heading" aria-busy={pending}>
    <header className="settings-section-heading settings-section-tools"><div><h3 id="cleanup-health-heading">Content cleanup</h3><p>Expired and deleted reviews are inaccessible while stored content awaits removal.</p></div><RefreshButton label="Refresh cleanup status" pending={pending} onClick={() => { setHealth(null); setPending(true); setError(''); setAttempt(value => value + 1) }} /></header>
    {error && <InlineNotice error title="Cleanup status is unavailable">{error} Use Refresh to check the service again.</InlineNotice>}{!health && pending && <LoadingState label="Checking cleanup status…" compact />}{health && <CleanupStatus health={health} />}
    <p className="settings-footnote">Cleanup service status is shared across the installation. The review count is for this workspace.</p>
  </section>
}
