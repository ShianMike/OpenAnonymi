import { useEffect, useState } from 'react'
import { getWorkspaceActivity, type ActivityView, type SessionView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { eventName } from './events'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; value: ActivityView }

export function ActivityPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspaceActivity(workspaceId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', value })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({
        kind: 'error',
        message: cause instanceof Error ? cause.message : 'Activity could not be loaded.',
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  return (
    <section aria-labelledby="activity-title">
      <PageHeader title="Activity" titleId="activity-title"
        description="Recent review events in this workspace. Activity records contain no document text." />
      {session.memberships.length > 1 && (
        <div className="workspace-picker">
          <label htmlFor="activity-workspace">Workspace</label>{' '}
          <select id="activity-workspace" value={workspaceId} onChange={(event) => {
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
      {data.kind === 'loading' && <p role="status">Loading activity…</p>}
      {data.kind === 'error' && (
        <div role="alert">
          <p>{data.message}</p>
          <button type="button" onClick={() => {
            setData({ kind: 'loading' })
            setAttempt((value) => value + 1)
          }}>Retry activity</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <p className="data-scope">Your activity from {new Date(data.value.since).toLocaleString()} to {' '}
            {new Date(data.value.as_of).toLocaleString()}. Showing the latest {' '}
            {data.value.own_events.length} of {data.value.own_total} event(s).</p>
          {data.value.own_events.length === 0 ?
            <div className="empty-state surface-panel"><strong>No activity in this period</strong>
              <p>Events appear here as you work on reviews.</p></div> : (
            <div className="table-shell activity-table" role="region" aria-label="Recent activity" tabIndex={0}>
              <table><thead><tr><th scope="col">Event</th><th scope="col">Outcome</th>
                <th scope="col">When</th><th scope="col">Review</th></tr></thead>
                <tbody>{data.value.own_events.map((event, index) => (
                  <tr key={`${event.occurred_at}-${index}`}>
                    <th scope="row">{eventName(event.event_code)}</th>
                    <td><span className="mobile-cell-label">Outcome</span>{event.outcome}</td>
                    <td><span className="mobile-cell-label">When</span>{new Date(event.occurred_at).toLocaleString()}</td>
                    <td><span className="mobile-cell-label">Review</span>{event.document_id ? event.document_id.slice(0, 8) : '—'}</td>
                  </tr>
                ))}</tbody></table>
            </div>
          )}
          {data.value.workspace_counts && (
            <section className="surface-panel" aria-labelledby="activity-workspace-counts">
              <h2 id="activity-workspace-counts">Workspace event counts</h2>
              <p>All members in the same 30-day period; counts only.</p>
              {Object.keys(data.value.workspace_counts).length === 0 ? <p>No events.</p> : (
                <ul>{Object.entries(data.value.workspace_counts).map(([code, count]) => (
                  <li key={code}>{eventName(code)}: {count}</li>
                ))}</ul>
              )}
            </section>
          )}
        </>
      )}
    </section>
  )
}
