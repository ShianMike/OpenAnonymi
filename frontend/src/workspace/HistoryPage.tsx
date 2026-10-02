import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Clock3, FileClock, ListChecks } from 'lucide-react'
import { getDocumentHistory, type DocumentHistoryView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { PanelHeading } from '../ui/WorkspaceControls'
import { StatusBadge } from '../ui/StatusBadge'
import { RevisionComparison } from '../comparison/RevisionComparison'
import { eventName } from './events'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; value: DocumentHistoryView }

export function HistoryPage() {
  const { workspaceId, documentId } = useParams<{ workspaceId: string; documentId: string }>()
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspaceId || !documentId) return
    const controller = new AbortController()
    getDocumentHistory(workspaceId, documentId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', value })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'History could not be loaded.' })
    })
    return () => controller.abort()
  }, [workspaceId, documentId, attempt])
  return <section aria-labelledby="history-title">
    <PageHeader title="Review history" titleId="history-title" description="Follow the changes. See how this review came together."
      action={<Link to="/documents">Back to documents</Link>} />
    {data.kind === 'loading' && <LoadingState label="Loading review history…" description="Opening saved revisions and review actions." />}
    {data.kind === 'error' && <div role="alert"><p>{data.message}</p><button type="button" onClick={() => setAttempt(attempt + 1)}>Retry history</button></div>}
    {data.kind === 'ready' && <>
      <div className="history-meta">
        <StatusBadge status={data.value.status} />
        <span><Clock3 size={15} aria-hidden="true" /> Created {new Date(data.value.created_at).toLocaleString()}</span>
        <span>Expires {new Date(data.value.expires_at).toLocaleString()}</span>
        {data.value.status !== 'deleted' && data.value.status !== 'expired' && <Link to={`/documents/${data.value.document_id}/edit`}>Open current review</Link>}
        {data.value.deleted_at && <span>Deleted {new Date(data.value.deleted_at).toLocaleString()}</span>}
      </div>
      <RevisionComparison key={`${data.value.document_id}.${data.value.revision_total}`} history={data.value} />
      <section className="history-timeline workspace-panel" aria-label="Saved source revisions">
        <PanelHeading icon={FileClock} title="Source revisions" description={`Showing ${data.value.revisions.length} of ${data.value.revision_total} saved revisions.`} />
        {data.value.revisions.length === 0 ? <p className="field-note">No source revisions remain.</p> : <ol>
          {data.value.revisions.map((revision) => <li key={revision.id}>
            <span>Revision {revision.number} {revision.is_current && <span className="subtle-badge">Current</span>}</span>
            <time dateTime={revision.created_at}>{new Date(revision.created_at).toLocaleString()}</time>
          </li>)}
        </ol>}
      </section>
      <section className="history-timeline workspace-panel" aria-label="Review actions">
        <PanelHeading icon={ListChecks} title="Actions" description={`Latest ${data.value.events.length} of ${data.value.event_total} retained actions.`} />
        <p className="field-note">Action history contains no source values or replacement mapping.</p>
        {data.value.events.length === 0 ? <p className="field-note">No retained actions.</p> : <ol>
          {data.value.events.map((event, index) => <li key={`${event.occurred_at}-${index}`}>
            <span>{eventName(event.event_code)} · {event.outcome}</span>
            <time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time>
          </li>)}
        </ol>}
      </section>
    </>}
  </section>
}
