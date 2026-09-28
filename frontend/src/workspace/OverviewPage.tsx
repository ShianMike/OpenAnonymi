import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getWorkspaceOverview, type OverviewView, type SessionView,
} from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { StatusBadge } from '../ui/StatusBadge'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; value: OverviewView }

export function OverviewPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspaceOverview(workspaceId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', value })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({
        kind: 'error',
        message: cause instanceof Error ? cause.message : 'Overview could not be loaded.',
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  return (
    <section aria-labelledby="overview-title">
      <PageHeader title="Overview" titleId="overview-title"
        description="Your review work and recent progress in this workspace."
        action={<Link className="button-primary" to="/new">New review</Link>} />
      {session.memberships.length > 1 && (
        <div className="workspace-picker">
          <label htmlFor="overview-workspace">Workspace</label>
          <select id="overview-workspace" value={workspaceId} onChange={(event) => {
            setWorkspaceId(event.target.value)
            setData({ kind: 'loading' })
          }}>
            {session.memberships.map((membership, index) => (
              <option key={membership.workspace_id} value={membership.workspace_id}>
                {membership.workspace_name || `Workspace ${index + 1}`}
              </option>
            ))}
          </select>
        </div>
      )}
      {data.kind === 'loading' && <p role="status">Loading your review counts…</p>}
      {data.kind === 'error' && (
        <div role="alert">
          <p>{data.message}</p>
          <button type="button" onClick={() => {
            setData({ kind: 'loading' })
            setAttempt((value) => value + 1)
          }}>Retry overview</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <p className="data-scope">Your non-deleted documents as of {' '}
            {new Date(data.value.as_of).toLocaleString()}.</p>
          <div className="overview-metrics">
            <article className="metric-card">
              <span>Your reviews</span><strong>{data.value.own_total.toLocaleString()}</strong>
              <small>Non-deleted documents</small>
            </article>
            <article className="metric-card">
              <span>Created recently</span>
              <strong>{data.value.own_created_last_30_days.toLocaleString()}</strong>
              <small>Last 30 days</small>
            </article>
            {data.value.workspace_total !== null && (
              <article className="metric-card">
                <span>Workspace total</span>
                <strong>{data.value.workspace_total.toLocaleString()}</strong>
                <small>All members, counts only</small>
              </article>
            )}
          </div>
          <section className="surface-panel" aria-labelledby="overview-status-heading">
            <div className="section-heading"><div>
              <h2 id="overview-status-heading">Review statuses</h2>
              <p>See where your documents need attention.</p>
            </div><Link to="/documents">View documents</Link></div>
            {Object.keys(data.value.own_by_status).length === 0 ? (
              <div className="empty-state"><strong>No reviews yet</strong>
                <p>Start with pasted text or a UTF-8 TXT file, then review every finding.</p>
                <Link to="/new">Create your first review</Link>
              </div>
            ) : (
              <ul className="status-list">{Object.entries(data.value.own_by_status).map(([status, count]) => (
                <li key={status}><StatusBadge status={status} /><strong>{count.toLocaleString()}</strong></li>
              ))}</ul>
            )}
          </section>
        </>
      )}
    </section>
  )
}
