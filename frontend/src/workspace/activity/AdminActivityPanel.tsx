import { useEffect, useRef, useState } from 'react'
import { Download, History } from 'lucide-react'
import { ApiRequestError, downloadAdminActivity, getAdminActivity, type AdminActivityView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { categoryPresentation } from '../../rules/categoryPresentation'
import { activityEventCodes, eventName } from '../events'
import './admin-activity.css'

const fixedName = (value: string | null) => value ? value.replaceAll('_', ' ') : 'Undecided'

export function AdminActivityPanel({ workspaceId, csrf, onAccessLost }: { workspaceId: string; csrf: string; onAccessLost: () => void }) {
  const [days, setDays] = useState(30)
  const [eventCode, setEventCode] = useState('')
  const [value, setValue] = useState<AdminActivityView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const request = useRef<AbortController | null>(null)
  const exportRequest = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    request.current = controller
    getAdminActivity(workspaceId, { days, limit: 50, event_code: eventCode || null }, csrf, controller.signal)
      .then(result => { if (!controller.signal.aborted) setValue(result) })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) { setValue(null); onAccessLost() }
        setError(cause instanceof Error ? cause.message : 'Workspace activity could not be loaded.')
      })
      .finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => { controller.abort(); request.current?.abort(); exportRequest.current?.abort() }
  }, [workspaceId, csrf, days, eventCode, attempt, onAccessLost])
  function resetLoading() {
    request.current?.abort()
    setValue(null); setError(null); setPending(true)
  }
  function refresh() {
    resetLoading(); setAttempt(current => current + 1)
  }
  async function more() {
    if (!value?.next_cursor || pending) return
    setPending(true); setError(null)
    const controller = new AbortController()
    request.current = controller
    try {
      const next = await getAdminActivity(workspaceId, { days, limit: 50, event_code: eventCode || null, cursor: value.next_cursor }, csrf, controller.signal)
      if (!controller.signal.aborted) setValue(current => current ? {
        ...next, events: [...current.events, ...next.events.filter(row => !current.events.some(previous => previous.id === row.id))],
      } : next)
    } catch (cause) { failure(cause, controller) }
    finally { if (!controller.signal.aborted) setPending(false) }
  }
  function failure(cause: unknown, controller: AbortController) {
    if (controller.signal.aborted) return
    if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) { setValue(null); onAccessLost() }
    setError(cause instanceof Error ? cause.message : 'Workspace activity is unavailable.')
  }
  async function download() {
    if (exporting) return
    const controller = new AbortController()
    exportRequest.current = controller
    setExporting(true); setError(null)
    try {
      const file = await downloadAdminActivity(workspaceId, { days, limit: 50, event_code: eventCode || null }, csrf, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(file)
      const link = document.createElement('a'); link.href = url; link.download = 'workspace-activity.csv'; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) { failure(cause, controller) }
    finally { if (!controller.signal.aborted) setExporting(false) }
  }
  return <section className="surface-panel admin-activity" aria-labelledby="admin-activity-heading">
    <div className="section-heading"><div>
      <h2 id="admin-activity-heading"><History size={18} aria-hidden="true" /> Workspace activity</h2>
      <p>Administrator view of member actions and fixed decision changes.</p>
    </div><button type="button" disabled={pending || exporting || !value} onClick={() => void download()}>
      <Download size={15} aria-hidden="true" /> {exporting ? 'Preparing CSV…' : 'Download activity CSV'}
    </button></div>
    <p className="admin-activity-scope">Member and review IDs identify events. This view excludes source text, titles, matched values, labels, comments and Keep reasons. Decision changes are recorded from this update onward.</p>
    <div className="admin-activity-filters">
      <div><label htmlFor="admin-activity-days">Period</label><GlassSelect id="admin-activity-days" value={days} disabled={exporting} onValueChange={choice => { if (Number(choice) !== days) { resetLoading(); setDays(Number(choice)) } }}>
        {[1, 7, 30, 90].map(day => <option key={day} value={day}>Last {day} day{day === 1 ? '' : 's'}</option>)}
      </GlassSelect></div>
      <div><label htmlFor="admin-activity-code">Workspace event</label><GlassSelect id="admin-activity-code" value={eventCode} disabled={exporting} onValueChange={choice => { if (choice !== eventCode) { resetLoading(); setEventCode(choice) } }}>
        <option value="">All events</option>{activityEventCodes.map(code => <option key={code} value={code}>{eventName(code)}</option>)}
      </GlassSelect></div>
      <button type="button" disabled={pending || exporting} onClick={refresh}>Refresh workspace activity</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {pending && !value && <p role="status">Loading workspace activity…</p>}
    {value && <>
      <p className="admin-activity-scope">Since {new Date(value.since).toLocaleString()}, within this workspace’s activity retention. CSV includes the selected period and event type, up to 1,000 events and 8 MiB.</p>
      {value.events.length === 0 ? <div className="empty-state"><strong>No workspace events in this period</strong></div> : <ol className="admin-event-list">
        {value.events.map(row => <li key={row.id}>
          <div className="admin-event-heading"><strong>{eventName(row.event_code)}</strong><time dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString()}</time></div>
          <p className="admin-event-ids">{row.actor_id ? `Member ${row.actor_id}` : 'System or removed member'}{row.document_id && <> · Review {row.document_id}</>} · {row.outcome}</p>
          {row.decision_changes.length > 0 && <details className="admin-decision-diff"><summary>{row.decision_change_count} decision change{row.decision_change_count === 1 ? '' : 's'} · version {row.decision_version}</summary>
            <ul>{row.decision_changes.map(change => <li key={change.finding_id}>
              <strong>{categoryPresentation[change.category].label}</strong>
              <span>{fixedName(change.before_action)}{change.before_style && ` · ${fixedName(change.before_style)}`}{change.before_option && ` · ${fixedName(change.before_option)}`} → {fixedName(change.after_action)}{change.after_style && ` · ${fixedName(change.after_style)}`}{change.after_option && ` · ${fixedName(change.after_option)}`}</span>
              <small>Finding {change.finding_id}</small>
            </li>)}</ul>
            {row.decision_change_count > row.decision_changes.length && <p>Details record the first {row.decision_changes.length} of {row.decision_change_count} changes.</p>}
          </details>}
        </li>)}
      </ol>}
      {value.next_cursor && <button type="button" disabled={pending || exporting} onClick={() => void more()}>{pending ? 'Loading more…' : 'Load more workspace events'}</button>}
      <p className="admin-activity-scope">{value.events.length} events loaded.</p>
    </>}
    {!pending && !value && error && <button type="button" onClick={refresh}>Retry workspace activity</button>}
  </section>
}
