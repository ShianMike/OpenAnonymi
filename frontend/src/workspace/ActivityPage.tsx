import { useEffect, useState } from 'react'
import { getWorkspaceActivity, type ActivityView, type SessionView } from '../api/client'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; value: ActivityView }

function eventName(code: string): string {
  const names: Record<string, string> = {
    document_created: 'Review created',
    source_revised: 'Source revised',
    review_completed: 'Review confirmed',
    output_copied: 'Reviewed text copied',
    output_generated: 'Reviewed TXT generated',
    document_deleted: 'Review deleted',
    document_expired: 'Review expired',
    preset_created: 'Rules preset created',
    preset_updated: 'Rules preset updated',
    scan_settings_changed: 'Suggestion settings changed',
    scan_completed: 'Suggestions finished',
    scan_failed: 'Suggestions failed',
    review_decision_saved: 'Finding decision saved',
    workspace_settings_changed: 'Workspace settings changed',
    member_invited: 'Member invited',
    member_role_changed: 'Member role changed',
    member_revoked: 'Member access revoked',
    member_restored: 'Member access restored',
  }
  return names[code] || code.replaceAll('_', ' ')
}

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
      <h1 id="activity-title">Activity</h1>
      {session.memberships.length > 1 && (
        <>
          <label htmlFor="activity-workspace">Workspace</label>{' '}
          <select id="activity-workspace" value={workspaceId} onChange={(event) => {
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
          <p>Your activity from {new Date(data.value.since).toLocaleString()} to {' '}
            {new Date(data.value.as_of).toLocaleString()}. Showing the latest {' '}
            {data.value.own_events.length} of {data.value.own_total} event(s).</p>
          {data.value.own_events.length === 0 ? <p>No activity in this period.</p> : (
            <ol>{data.value.own_events.map((event, index) => (
              <li key={`${event.occurred_at}-${index}`}>
                {eventName(event.event_code)} — {event.outcome}, {' '}
                {new Date(event.occurred_at).toLocaleString()}
                {event.document_id && `; review ${event.document_id.slice(0, 8)}`}
              </li>
            ))}</ol>
          )}
          {data.value.workspace_counts && (
            <>
              <h2>Workspace event counts</h2>
              <p>All members in the same 30-day period; counts only.</p>
              {Object.keys(data.value.workspace_counts).length === 0 ? <p>No events.</p> : (
                <ul>{Object.entries(data.value.workspace_counts).map(([code, count]) => (
                  <li key={code}>{eventName(code)}: {count}</li>
                ))}</ul>
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}
