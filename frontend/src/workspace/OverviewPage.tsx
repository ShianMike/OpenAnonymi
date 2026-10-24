import { useEffect, useState } from 'react'
import { ArrowRight, CheckCheck, CircleAlert, Clock3, FileCheck2, Files, Plus, SlidersHorizontal } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiRequestError, getWorkspaceOverview, type OverviewView, type SessionView } from '../api/client'
import { RefreshButton } from '../ui/WorkspaceControls'
import { StatusBadge } from '../ui/StatusBadge'
import { LoadingState } from '../loading/LoadingState'
import { OverviewAnalytics } from './overview/OverviewAnalytics'
import { RecentReviews } from './overview/RecentReviews'
import { reviewsInProgress } from './overview/overviewPresentation'
import { useReviewWorkspace } from '../resume/reviewWorkspace'

type Data = { kind: 'loading' } | { kind: 'error'; workspaceId: string; message: string }
  | { kind: 'ready'; workspaceId: string; value: OverviewView }

export function OverviewPage({ session }: { session: SessionView }) {
  const [params] = useSearchParams()
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
  const continueReview = `/documents${query}&view=in_progress`

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
      <div><h1 id="overview-title">Overview</h1><p>Everything you need to keep your reviews moving.</p></div>
      <div className="overview-heading-actions">
        <RefreshButton label="Refresh overview" onClick={refresh} disabled={!workspaceId || data.kind === 'loading'} pending={refreshing} />
        {workspaceId && <Link className="overview-primary-action" to={newReview}><Plus size={17} aria-hidden="true" /> New review</Link>}
      </div>
    </header>
    {!workspaceId && <div className="overview-error" role="alert"><CircleAlert size={19} aria-hidden="true" />
      <p>You don’t have access to a workspace. Contact your workspace administrator.</p>
    </div>}
    {workspaceId && !value && (data.kind !== 'error' || data.workspaceId !== workspaceId) &&
      <LoadingState label="Loading your review counts…" shape="cards" description="Bringing together your reviews and recent progress." onRetry={refresh} />}
    {data.kind === 'error' && data.workspaceId === workspaceId && <div className="overview-error" role="alert">
      <CircleAlert size={19} aria-hidden="true" /><p>{data.message}</p>
      <button type="button" disabled={refreshing} onClick={refresh}>Retry overview</button>
    </div>}
    {value && refreshError && <div className="overview-error" role="alert"><CircleAlert size={19} aria-hidden="true" />
      <p>{refreshError} Showing the last successful update.</p><button type="button" disabled={refreshing} onClick={refresh}>Try again</button>
    </div>}
    {refreshing && <span className="sr-only" role="status">Refreshing overview</span>}
    {value && <>
      <div className="overview-scope"><span>Your reviews <span aria-hidden="true">/</span> {workspace?.workspace_name || 'Workspace'}</span>
        <time dateTime={value.as_of} title={new Date(value.as_of).toLocaleString()}>{refreshing ? 'Updating…' : `Updated ${new Date(value.as_of).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}</time>
      </div>
      <dl className="overview-stats">
        <div><dt><Files size={16} aria-hidden="true" />Total reviews</dt><dd>{value.own_total.toLocaleString()}<small>{value.own_created_last_30_days.toLocaleString()} created in the last 30 days</small></dd></div>
        <div><dt><Clock3 size={16} aria-hidden="true" />In progress</dt><dd>{reviewsInProgress(value.own_by_status).toLocaleString()}<small>Drafts and reviews to finish</small></dd></div>
        <div><dt><FileCheck2 size={16} aria-hidden="true" />Ready to share</dt><dd>{(value.own_by_status.ready ?? 0).toLocaleString()}<small>Confirmed, ready for export</small></dd></div>
        <div><dt><CheckCheck size={16} aria-hidden="true" />Exported</dt><dd>{(value.own_by_status.exported ?? 0).toLocaleString()}<small>Reviews with an export</small></dd></div>
      </dl>
      <div className="overview-work-grid">
        <RecentReviews key={`${workspaceId}:${attempt}:${session.csrf_token}`} workspaceId={workspaceId} />
        <section className="overview-status-panel" aria-labelledby="overview-status-heading">
          <header className="overview-card-heading"><div><h2 id="overview-status-heading">Review status</h2><p>All your non-deleted reviews.</p></div></header>
          {value.own_total > 0 ? <>
            <div className="overview-status-bar" aria-hidden="true">{Object.entries(value.own_by_status).map(([status, count]) =>
              <span key={status} data-status={status} style={{ flex: count }} />)}</div>
            <ul className="overview-status-list">{Object.entries(value.own_by_status).map(([status, count]) =>
              <li key={status}><StatusBadge status={status} /><strong>{count.toLocaleString()}</strong></li>)}</ul>
            {(value.own_by_status.expired ?? 0) > 0 && <p className="overview-status-note">Expired reviews are no longer available to open.</p>}
          </> : <p className="overview-status-note">Your review statuses will appear here after you create a draft.</p>}
          {value.workspace_total !== null && <div className="overview-workspace-total"><span>Across this workspace<small>All members · counts only</small></span><strong>{value.workspace_total.toLocaleString()}</strong></div>}
        </section>
      </div>
      <nav className="overview-shortcuts" aria-label="Review shortcuts">
        <Link to={continueReview}><span><Clock3 size={17} aria-hidden="true" /><strong>Continue a review</strong></span><small>Find your unfinished work in Documents</small><ArrowRight size={17} aria-hidden="true" /></Link>
        <Link to={`/rules${query}`}><span><SlidersHorizontal size={17} aria-hidden="true" /><strong>Review rules</strong></span><small>Manage how personal details are found</small><ArrowRight size={17} aria-hidden="true" /></Link>
      </nav>
      <OverviewAnalytics value={value.analytics} />
    </>}
  </section>
}
