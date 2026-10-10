import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, Clock3, FileClock, FileText, ListChecks, ShieldCheck } from 'lucide-react'
import { getDocumentHistory, type DocumentHistoryView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { PanelHeading } from '../ui/WorkspaceControls'
import { StatusBadge } from '../ui/StatusBadge'
import { ListPagination } from '../ui/ListPagination'
import { pageWindow } from '../ui/pagination'
import { RevisionComparison } from '../comparison/RevisionComparison'
import { eventName } from './events'
import { eventIcon, periodLabel } from './activity/activityPresentation'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; value: DocumentHistoryView }
const HISTORY_PAGE_SIZE = 5

export function HistoryPage() {
  const { workspaceId, documentId } = useParams<{ workspaceId: string; documentId: string }>()
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [revisionPage, setRevisionPage] = useState(0)
  const [actionPage, setActionPage] = useState(0)
  const revisions = pageWindow(data.kind === 'ready' ? data.value.revisions.length : 0, revisionPage, HISTORY_PAGE_SIZE)
  const actions = pageWindow(data.kind === 'ready' ? data.value.events.length : 0, actionPage, HISTORY_PAGE_SIZE)
  useEffect(() => {
    if (!workspaceId || !documentId) return
    const controller = new AbortController()
    getDocumentHistory(workspaceId, documentId, controller.signal).then((value) => {
      if (!controller.signal.aborted) {
        setData({ kind: 'ready', value }); setRevisionPage(0); setActionPage(0)
      }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'History could not be loaded.' })
    })
    return () => controller.abort()
  }, [workspaceId, documentId, attempt])
  return <section className="history-page" aria-labelledby="history-title">
    <PageHeader title="Review history" titleId="history-title" description="Compare saved versions and follow the decisions made along the way."
      action={<Link className="history-back" to="/documents"><ArrowLeft size={16} aria-hidden="true" />Back to documents</Link>} />
    {data.kind === 'loading' && <LoadingState label="Loading review history…" description="Opening saved revisions and review actions." />}
    {data.kind === 'error' && <div role="alert"><p>{data.message}</p><button type="button" onClick={() => setAttempt(attempt + 1)}>Retry history</button></div>}
    {data.kind === 'ready' && <>
      <div className="history-meta">
        <StatusBadge status={data.value.status} />
        <span><FileClock size={15} aria-hidden="true" /> Created <time dateTime={data.value.created_at} title={new Date(data.value.created_at).toLocaleString()}>{periodLabel(data.value.created_at)}</time></span>
        <span><Clock3 size={15} aria-hidden="true" /> Available until <time dateTime={data.value.expires_at} title={new Date(data.value.expires_at).toLocaleString()}>{periodLabel(data.value.expires_at)}</time></span>
        {data.value.status !== 'deleted' && data.value.status !== 'expired' && <Link to={`/documents/${data.value.document_id}/edit`}>Open current review<ArrowUpRight size={16} aria-hidden="true" /></Link>}
        {data.value.deleted_at && <span>Deleted {new Date(data.value.deleted_at).toLocaleString()}</span>}
      </div>
      <RevisionComparison key={`${data.value.document_id}.${data.value.revision_total}`} history={data.value} />
      <div className="history-details-grid">
      <section className="history-timeline history-revisions workspace-panel" aria-label="Saved source revisions">
        <PanelHeading icon={FileClock} title="Saved versions" description={`${data.value.revisions.length} of ${data.value.revision_total} versions · newest first`} />
        {data.value.revisions.length === 0 ? <p className="field-note">No source revisions remain.</p> : <ol key={revisions.page} start={revisions.start + 1}>
          {data.value.revisions.slice(revisions.start, revisions.end).map((revision) => <li key={revision.id} data-current={revision.is_current || undefined}>
            <span className="history-entry-icon"><FileText size={17} aria-hidden="true" /></span>
            <div className="history-entry-copy">
              <strong>Revision {revision.number}</strong>
              <time dateTime={revision.created_at}>{periodLabel(revision.created_at)} · {new Date(revision.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
            </div>
            {revision.is_current && <span className="subtle-badge">Current</span>}
          </li>)}
        </ol>}
        <ListPagination page={revisions.page} total={data.value.revisions.length} pageSize={HISTORY_PAGE_SIZE} label="Versions"
          onPrevious={() => setRevisionPage(revisions.page - 1)} onNext={() => setRevisionPage(revisions.page + 1)} />
        <p className="history-card-note">Saved versions contain your original source text.</p>
      </section>
      <section className="history-timeline history-actions workspace-panel" aria-label="Review actions">
        <PanelHeading icon={ListChecks} title="Review actions" description={`${data.value.events.length} of ${data.value.event_total} retained actions · newest first`} />
        {data.value.events.length === 0 ? <p className="field-note">No retained actions.</p> : <ol key={actions.page} start={actions.start + 1}>
          {data.value.events.slice(actions.start, actions.end).map((event, index) => {
            const Icon = eventIcon(event.event_code)
            return <li key={`${event.occurred_at}-${index}`}>
              <span className="history-entry-icon"><Icon size={17} aria-hidden="true" /></span>
              <div className="history-entry-copy">
                <strong>{eventName(event.event_code)}</strong>
                <time dateTime={event.occurred_at}>{periodLabel(event.occurred_at)} · {new Date(event.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
              </div>
              <span className="history-outcome" data-outcome={event.outcome}>{event.outcome}</span>
            </li>
          })}
        </ol>}
        <ListPagination page={actions.page} total={data.value.events.length} pageSize={HISTORY_PAGE_SIZE} label="Actions"
          onPrevious={() => setActionPage(actions.page - 1)} onNext={() => setActionPage(actions.page + 1)} />
        <p className="history-card-note"><ShieldCheck size={15} aria-hidden="true" />Source values and replacement mappings aren’t recorded here.</p>
      </section>
      </div>
    </>}
  </section>
}
