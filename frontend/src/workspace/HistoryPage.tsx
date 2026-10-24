import * as Tabs from '@radix-ui/react-tabs'
import { useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, CircleAlert, Clock3, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react'
import { LoadingState } from '../loading/LoadingState'
import { StatusBadge } from '../ui/StatusBadge'
import { ListPagination } from '../ui/ListPagination'
import { pageWindow } from '../ui/pagination'
import { RevisionComparison } from '../comparison/RevisionComparison'
import { eventName } from './events'
import { periodLabel } from './activity/activityPresentation'
import { historyAvailable, historyDays } from './history/historyPresentation'
import { useHistory } from './history/useHistory'
import './history/history.css'

const ACTION_PAGE_SIZE = 12

export function HistoryPage() {
  const { workspaceId = '', documentId = '' } = useParams<{ workspaceId: string; documentId: string }>()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const { data, retry } = useHistory(workspaceId, documentId)
  const [actionPage, setActionPage] = useState(0)
  const history = data.kind === 'ready' ? data.value : null
  const currentVersion = history?.revisions.find(revision => revision.is_current)
  const available = data.kind === 'ready' && historyAvailable(data.value, Date.parse(data.checkedAt))
  const view = available && params.get('view') === 'versions' ? 'versions' : 'activity'
  const range = pageWindow(history?.events.length ?? 0, actionPage, ACTION_PAGE_SIZE)
  const days = history && data.kind === 'ready' ? historyDays(history.events.slice(range.start, range.end), data.checkedAt) : []
  const returnParams = new URLSearchParams(typeof location.state?.documentsSearch === 'string' ? location.state.documentsSearch : '')
  returnParams.set('workspace', workspaceId)
  const documentsSearch = returnParams.toString()
  const documentsHref = `/documents?${documentsSearch}`
  const status = history?.status === 'deleted' ? 'deleted' : !available && history ? 'expired' : history?.status

  return <section className="history-page" aria-labelledby="history-title">
    <Link className="history-back" to={documentsHref}><ArrowLeft size={14} aria-hidden="true" />Documents</Link>
    <header className="history-heading">
      <div><h1 id="history-title">Review history</h1><p>The changes and decisions behind this review.</p></div>
      {available && <Link className="history-open-review" to={`/documents/${documentId}/edit`} state={{ documentsSearch }}>Open review<ArrowUpRight size={15} aria-hidden="true" /></Link>}
    </header>
    {data.kind === 'loading' && <LoadingState label="Loading review history…" description="Checking saved versions and retained activity." shape="timeline" onRetry={retry} />}
    {data.kind === 'error' && <div className="history-error" role="alert"><CircleAlert size={24} aria-hidden="true" /><h2>History couldn’t be loaded</h2><p>{data.message}</p><button type="button" onClick={retry}>Try again</button></div>}
    {history && <>
      {!available && <div className="history-availability" role="status">
        <LockKeyhole size={17} aria-hidden="true" /><div><strong>{status === 'deleted' ? 'This review was deleted' : 'This review has expired'}</strong><p>Source text and saved versions are unavailable. Retained review activity is still shown below.</p></div>
      </div>}
      <Tabs.Root value={view} onValueChange={next => {
        const search = new URLSearchParams(params)
        if (next === 'versions') search.set('view', 'versions'); else search.delete('view')
        setParams(search, { replace: true, state: location.state })
      }}>
        <div className="history-view-bar">
          <Tabs.List className="history-views" aria-label="History views">
            <Tabs.Trigger value="activity">Activity<span>{history.event_total}</span></Tabs.Trigger>
            <Tabs.Trigger value="versions" disabled={!available} aria-describedby={!available ? 'history-versions-unavailable' : undefined}>Versions<span>{available ? history.revision_total : 0}</span></Tabs.Trigger>
          </Tabs.List>
          <button type="button" className="history-refresh" aria-label="Refresh history" title="Refresh history" onClick={retry}><RefreshCw size={15} aria-hidden="true" /></button>
        </div>
        {!available && <span className="sr-only" id="history-versions-unavailable">Saved versions are unavailable because the review has expired or was deleted.</span>}
        <Tabs.Content value="activity" className="history-view-content">
          <div className="history-activity-layout">
            <section className="history-feed" aria-label="Review activity">
              <div className="history-feed-heading"><h2>Review activity</h2><span>Newest first</span></div>
              {history.events.length === 0 ? <div className="history-empty"><Clock3 size={24} strokeWidth={1.5} aria-hidden="true" /><h3>No retained activity</h3><p>Review actions will appear here as you work.</p></div>
                : days.map(day => <section className="history-day" key={day.key} aria-label={day.label}>
                  <h3>{day.label}</h3>
                  <ol>{day.events.map((event, index) => <li key={`${event.occurred_at}.${event.event_code}.${index}`} data-outcome={event.outcome} data-milestone={['review_completed', 'output_generated', 'output_copied'].includes(event.event_code) || undefined}>
                    <span className="history-event-dot" aria-hidden="true" />
                    <div className="history-event-copy"><strong>{eventName(event.event_code)}</strong>
                      <span className={event.outcome === 'completed' ? 'sr-only' : 'history-event-outcome'} data-outcome={event.outcome}>{event.outcome.replaceAll('_', ' ')}</span>
                    </div>
                    <time dateTime={event.occurred_at} title={new Date(event.occurred_at).toLocaleString()}>{new Date(event.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
                  </li>)}</ol>
                </section>)}
              {history.events.length > ACTION_PAGE_SIZE && <ListPagination page={range.page} total={history.events.length} pageSize={ACTION_PAGE_SIZE} label="Actions" onPrevious={() => setActionPage(range.page - 1)} onNext={() => setActionPage(range.page + 1)} />}
              {history.event_total > history.events.length && <p className="history-limit-note">Showing the latest {history.events.length} of {history.event_total} retained actions.</p>}
              <p className="history-privacy-note"><ShieldCheck size={14} aria-hidden="true" />Activity contains action metadata. Source text and replacement values aren’t included.</p>
            </section>
            <aside className="history-about" aria-labelledby="history-about-heading">
              <h2 id="history-about-heading">About this review</h2>
              <dl>
                <div><dt>Status</dt><dd><StatusBadge status={status ?? 'draft'} /></dd></div>
                <div><dt>Created</dt><dd><time dateTime={history.created_at} title={new Date(history.created_at).toLocaleString()}>{periodLabel(history.created_at)}</time></dd></div>
                <div><dt>{status === 'deleted' ? 'Deleted' : available ? 'Available until' : 'Retention ended'}</dt><dd><time dateTime={history.deleted_at ?? history.expires_at} title={new Date(history.deleted_at ?? history.expires_at).toLocaleString()}>{periodLabel(history.deleted_at ?? history.expires_at)}</time></dd></div>
                {available && <div><dt>Current version</dt><dd>{currentVersion ? `Version ${currentVersion.number}` : 'No saved version'}</dd></div>}
              </dl>
              {available && history.revisions.length > 0 && <button type="button" className="history-see-versions" onClick={() => setParams(current => { const next = new URLSearchParams(current); next.set('view', 'versions'); return next }, { replace: true, state: location.state })}>Browse saved versions<ArrowUpRight size={14} aria-hidden="true" /></button>}
            </aside>
          </div>
        </Tabs.Content>
        <Tabs.Content value="versions" className="history-view-content">
          {available && <RevisionComparison key={`${documentId}.${history.revision_total}`} history={history} />}
        </Tabs.Content>
      </Tabs.Root>
    </>}
  </section>
}
