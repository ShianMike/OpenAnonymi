import { useEffect, useState } from 'react'
import { ArrowRight, ArrowUpRight, Building2, CircleAlert, Clock3, FilePlus2, FileText, Files, Layers2, ScanLine } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiRequestError, getWorkspaceOverview, type OverviewView, type SessionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { RefreshButton } from '../ui/WorkspaceControls'
import { StatusBadge } from '../ui/StatusBadge'
import { LoadingState } from '../loading/LoadingState'
import { OverviewAnalytics } from './overview/OverviewAnalytics'
import { useReviewWorkspace } from '../resume/reviewWorkspace'

type Data = { kind: 'loading' } | { kind: 'error'; workspaceId: string; message: string }
  | { kind: 'ready'; workspaceId: string; value: OverviewView }

export function OverviewPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const preferred = useReviewWorkspace(session.user_id)
  const workspace = session.memberships.find((item) => item.workspace_id === params.get('workspace'))
    ?? session.memberships.find(item => item.workspace_id === preferred) ?? session.memberships[0]
  const workspaceId = workspace?.workspace_id ?? ''
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const value = data.kind === 'ready' && data.workspaceId === workspaceId ? data.value : null
  const query = `?workspace=${encodeURIComponent(workspaceId)}`
  const newReview = `/new${query}`
  const documents = `/documents${query}`
  const continueReview = `/continue${query}`

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspaceOverview(workspaceId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setData({ kind: 'ready', workspaceId, value: result })
          setRefreshError(null)
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        const message = cause instanceof ApiRequestError && cause.status < 500 ? cause.message
          : 'We couldn’t load your overview. Check your connection and try again.'
        const denied = cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)
        setRefreshError(message)
        setData((current) => !denied && current.kind === 'ready' && current.workspaceId === workspaceId
          ? current : { kind: 'error', workspaceId, message })
      })
      .finally(() => { if (!controller.signal.aborted) setRefreshing(false) })
    return () => controller.abort()
  }, [workspaceId, attempt, session.csrf_token])

  function refresh() {
    setRefreshing(true)
    setRefreshError(null)
    setAttempt((current) => current + 1)
  }

  return <section className="overview-page" aria-labelledby="overview-title">
    <header className="overview-heading">
      <div>
        <h1 id="overview-title">Overview</h1>
        <p>A clear place to start, continue, and finish your reviews.</p>
      </div>
      <div className="overview-heading-tools">
        {session.memberships.length > 1 ? <div className="workspace-picker">
          <div className="overview-picker-label"><label htmlFor="overview-workspace">Workspace</label>
            {workspace && <span className="overview-role">{workspace.role === 'administrator' ? 'Admin' : 'Member'}</span>}
          </div>
          <GlassSelect id="overview-workspace" value={workspaceId} onValueChange={(id) => {
            if (id === workspaceId) return
            setData({ kind: 'loading' })
            setRefreshError(null)
            setParams((current) => { const next = new URLSearchParams(current); next.set('workspace', id); return next }, { replace: true })
          }}>
            {session.memberships.map((item, index) => <option key={item.workspace_id} value={item.workspace_id}>
              {item.workspace_name || `Workspace ${index + 1}`}
            </option>)}
          </GlassSelect>
        </div> : <div className="overview-workspace-label"><Building2 size={15} aria-hidden="true" />
          <span>{workspace?.workspace_name ?? 'Your workspace'}</span>
          {workspace && <span className="overview-role">{workspace.role === 'administrator' ? 'Admin' : 'Member'}</span>}
        </div>}
        <div className="overview-refresh-tools">
          {value && <time className="overview-updated" dateTime={value.as_of} title={new Date(value.as_of).toLocaleString()}>
            {refreshing ? 'Updating…' : `Updated ${new Date(value.as_of).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}
          </time>}
          <RefreshButton label="Refresh overview" onClick={refresh} disabled={!workspaceId || data.kind === 'loading'} pending={refreshing} />
        </div>
      </div>
    </header>
    {!workspaceId && <div className="overview-error" role="alert"><CircleAlert size={19} aria-hidden="true" />
      <p>You don’t have access to a workspace. Contact your workspace administrator.</p>
    </div>}
    {workspaceId && !value && (data.kind !== 'error' || data.workspaceId !== workspaceId) &&
      <LoadingState label="Loading your review counts…" shape="cards" description="Bringing together your reviews and recent progress." />}
    {data.kind === 'error' && data.workspaceId === workspaceId && <div className="overview-error" role="alert">
      <CircleAlert size={19} aria-hidden="true" /><p>{data.message}</p>
      <button type="button" disabled={refreshing} onClick={refresh}>Retry overview</button>
    </div>}
    {value && refreshError && <div className="overview-error" role="alert"><CircleAlert size={19} aria-hidden="true" />
      <p>{refreshError} Showing the last successful update.</p><button type="button" disabled={refreshing} onClick={refresh}>Try again</button>
    </div>}
    {refreshing && <span className="sr-only" role="status">Refreshing overview</span>}
    {value && <>
      <div className="overview-launch-grid">
        <section className="overview-launch" aria-labelledby="start-heading">
          <div className="overview-launch-copy">
            <span className="overview-small-label">{value.own_total === 0 ? 'A fresh start' : 'Your next step'}</span>
            <h2 id="start-heading">{value.own_total === 0 ? <>Start with a draft.<br /><span>Share with care.</span></> : <>A little progress.<br /><span>A clearer story.</span></>}</h2>
            <p>{value.own_total === 0 ? 'Paste text or import a file. Review the personal details before you share.'
              : 'Pick up an unfinished review, or make space for your next draft.'}</p>
            <div className="overview-launch-actions">
              <Link className="button-primary" to={value.own_total === 0 ? newReview : continueReview}>
                {value.own_total === 0 ? <FilePlus2 size={18} aria-hidden="true" /> : <ScanLine size={18} aria-hidden="true" />}
                {value.own_total === 0 ? 'Create your first review' : 'Continue review'}<ArrowRight size={17} aria-hidden="true" />
              </Link>
              <Link className="overview-text-link" to={value.own_total === 0 ? '/welcome#try-review' : newReview}>
                {value.own_total === 0 ? 'Try the demo' : 'New review'}<ArrowUpRight size={15} aria-hidden="true" />
              </Link>
            </div>
          </div>
          <div className="overview-draft-art" aria-hidden="true">
            <div className="overview-paper overview-paper-back" />
            <div className="overview-paper"><FileText size={24} strokeWidth={1.3} /><span className="overview-paper-lines"><i /><i /><i /><i /></span>
              <span className="overview-paper-check"><ScanLine size={20} strokeWidth={1.6} /> Yours to review</span>
            </div>
          </div>
          <ol className="overview-launch-steps"><li><span>01</span> Import a draft</li><li><span>02</span> Decide what stays</li><li><span>03</span> Confirm & share</li></ol>
        </section>
        <section className="overview-review-list" aria-labelledby="overview-status-heading">
          <div className="overview-card-heading"><div><h2 id="overview-status-heading">Your reviews</h2><p>Where things stand.</p></div>
            <Link className="overview-arrow-link" to={documents} aria-label="View documents"><ArrowUpRight size={19} aria-hidden="true" /></Link>
          </div>
          {Object.keys(value.own_by_status).length === 0 ? <div className="overview-review-empty">
            <span className="overview-empty-icon"><Files size={27} strokeWidth={1.3} aria-hidden="true" /></span>
            <strong>A clean slate.</strong><p>Your saved reviews will appear here.</p>
            <Link className="overview-text-link" to={documents}>Open documents<ArrowRight size={15} aria-hidden="true" /></Link>
          </div> : <>
            <ul className="overview-status-list">{Object.entries(value.own_by_status).map(([status, count]) =>
              <li key={status}><StatusBadge status={status} /><strong>{count.toLocaleString()}</strong></li>)}</ul>
            <Link className="overview-text-link overview-list-link" to={documents}>View all documents<ArrowRight size={15} aria-hidden="true" /></Link>
          </>}
        </section>
      </div>
      <div className="overview-metrics overview-summary">
        <article><span className="overview-summary-icon"><FileText size={20} strokeWidth={1.5} aria-hidden="true" /></span>
          <div><span>Your reviews</span><strong>{value.own_total.toLocaleString()}</strong><small>Non-deleted documents</small></div></article>
        <article><span className="overview-summary-icon"><Clock3 size={20} strokeWidth={1.5} aria-hidden="true" /></span>
          <div><span>Created recently</span><strong>{value.own_created_last_30_days.toLocaleString()}</strong><small>Last 30 days</small></div></article>
        {value.workspace_total !== null && <article><span className="overview-summary-icon"><Layers2 size={20} strokeWidth={1.5} aria-hidden="true" /></span>
          <div><span>Workspace total</span><strong>{value.workspace_total.toLocaleString()}</strong><small>All members · counts only</small></div></article>}
      </div>
      <OverviewAnalytics value={value.analytics} />
    </>}
  </section>
}
