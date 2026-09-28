import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getWorkspaceOverview, type OverviewView, type SessionView,
} from '../api/client'

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
      <h1 id="overview-title">Overview</h1>
      {session.memberships.length > 1 && (
        <>
          <label htmlFor="overview-workspace">Workspace</label>{' '}
          <select id="overview-workspace" value={workspaceId} onChange={(event) => {
            setWorkspaceId(event.target.value)
            setData({ kind: 'loading' })
          }}>
            {session.memberships.map((membership, index) => (
              <option key={membership.workspace_id} value={membership.workspace_id}>
                Workspace {index + 1}
              </option>
            ))}
          </select>
        </>
      )}
      <p><Link to="/new">New review</Link></p>
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
          <p>Counts for your documents in this workspace, excluding deleted documents.
            {' '}As of {new Date(data.value.as_of).toLocaleString()}.</p>
          <p>{data.value.own_total} total review(s); {' '}
            {data.value.own_created_last_30_days} created in the last 30 days.</p>
          <h2>Your review statuses</h2>
          {Object.keys(data.value.own_by_status).length === 0 ? (
            <p>No reviews yet.</p>
          ) : (
            <ul>{Object.entries(data.value.own_by_status).map(([status, count]) => (
              <li key={status}>{status.replaceAll('_', ' ')}: {count}</li>
            ))}</ul>
          )}
          {data.value.workspace_total !== null && (
            <p>Workspace total across all members: {data.value.workspace_total} review(s),
              excluding deleted documents. Member titles and content are not included.</p>
          )}
          <p><Link to="/documents">Open your documents</Link></p>
        </>
      )}
    </section>
  )
}
