import { useEffect, useRef, useState } from 'react'
import { Download } from 'lucide-react'
import { ApiRequestError, downloadAdminActivity, getAdminActivity, type AdminActivityView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { activityEventCodes, eventName } from '../events'
import { ActivityEmpty, ActivityPagination, ActivityTimeline } from './ActivityTimeline'
import { ACTIVITY_PAGE_SIZE, activityWindow, periodLabel, type DocumentMap } from './activityPresentation'

export function AdminActivityPanel({ workspaceId, csrf, refreshKey, onAccessLost, documents, currentUserId }: {
  workspaceId: string; csrf: string; refreshKey: number; onAccessLost: () => void; documents: DocumentMap; currentUserId: string
}) {
  const [days, setDays] = useState(30)
  const [eventCode, setEventCode] = useState('')
  const [value, setValue] = useState<AdminActivityView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [page, setPage] = useState(0)
  const [lastRefresh, setLastRefresh] = useState(refreshKey)
  if (lastRefresh !== refreshKey) {
    setLastRefresh(refreshKey)
    setValue(null); setError(null); setPending(true); setPage(0); setExporting(false)
  }
  const pageWindow = activityWindow(value?.events.length ?? 0, page)
  const request = useRef<AbortController | null>(null)
  const exportRequest = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    request.current = controller
    getAdminActivity(workspaceId, { days, limit: ACTIVITY_PAGE_SIZE, event_code: eventCode || null }, csrf, controller.signal)
      .then(result => { if (!controller.signal.aborted) setValue(result) })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) { setValue(null); onAccessLost() }
        setError(cause instanceof Error ? cause.message : 'Workspace activity could not be loaded.')
      })
      .finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => { controller.abort(); request.current?.abort(); exportRequest.current?.abort() }
  }, [workspaceId, csrf, days, eventCode, attempt, refreshKey, onAccessLost])
  function resetLoading() {
    request.current?.abort()
    setValue(null); setError(null); setPending(true); setPage(0)
  }
  function refresh() {
    resetLoading(); setAttempt(current => current + 1)
  }
  async function more() {
    if (pending) return
    if (value && pageWindow.end < value.events.length) { setPage(pageWindow.page + 1); heading.current?.focus(); return }
    if (!value?.next_cursor) return
    setPending(true); setError(null)
    const controller = new AbortController()
    request.current = controller
    try {
      const next = await getAdminActivity(workspaceId, { days, limit: ACTIVITY_PAGE_SIZE, event_code: eventCode || null, cursor: value.next_cursor }, csrf, controller.signal)
      if (!controller.signal.aborted) {
        setValue(current => current ? {
          ...next, events: [...current.events, ...next.events.filter(row => !current.events.some(previous => previous.id === row.id))],
        } : next)
        setPage(pageWindow.page + 1)
        heading.current?.focus()
      }
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
      const link = document.createElement('a'); link.href = url; link.download = 'workspace-activity.json'; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) { failure(cause, controller) }
    finally { if (!controller.signal.aborted) setExporting(false) }
  }
  return <section className="admin-activity" aria-labelledby="admin-activity-heading" aria-busy={pending}>
    <div className="activity-view-intro"><div><h2 ref={heading} tabIndex={-1} id="admin-activity-heading">Workspace log</h2><p>Recorded actions across your workspace. Available to administrators.</p></div></div>
    <div className="admin-activity-filters">
      <GlassSelect id="admin-activity-days" aria-label="Period" value={days} disabled={exporting} onValueChange={choice => { if (Number(choice) !== days) { resetLoading(); setDays(Number(choice)) } }}>
        {[1, 7, 30, 90].map(day => <option key={day} value={day}>Last {day} day{day === 1 ? '' : 's'}</option>)}
      </GlassSelect>
      <GlassSelect id="admin-activity-code" aria-label="Workspace event" value={eventCode} disabled={exporting} onValueChange={choice => { if (choice !== eventCode) { resetLoading(); setEventCode(choice) } }}>
        <option value="">All events</option>{activityEventCodes.map(code => <option key={code} value={code}>{eventName(code)}</option>)}
      </GlassSelect>
      {(eventCode || days !== 30) && <button type="button" className="activity-reset" disabled={exporting} onClick={() => { resetLoading(); setDays(30); setEventCode('') }}>Reset</button>}
      <button type="button" className="activity-button activity-export" disabled={pending || exporting || !value} onClick={() => void download()}>
        <Download size={14} aria-hidden="true" />{exporting ? 'Preparing…' : 'Export JSON'}
      </button>
    </div>
    {error && <InlineNotice error title="Workspace activity is unavailable" actions={<button type="button" className="activity-button" onClick={refresh} disabled={pending}>Retry workspace activity</button>}>{error}</InlineNotice>}
    {pending && !value && <p className="activity-pending" role="status">Loading workspace activity…</p>}
    {value && <>
      {pending && <p className="activity-pending" role="status">Loading next events…</p>}
      {value.events.length === 0 ? <ActivityEmpty filtered={!!eventCode || days !== 30} workspaceId={workspaceId} onClear={() => {
        resetLoading(); setDays(30); setEventCode('')
      }} /> : <><ActivityTimeline events={value.events.slice(pageWindow.start, pageWindow.end)} documents={documents} workspaceId={workspaceId} asOf={value.as_of} currentUserId={currentUserId} label="Workspace activity log" />
        <ActivityPagination page={pageWindow.page} total={value.events.length} hasMore={!!value.next_cursor} pending={pending || exporting}
          onPrevious={() => { setPage(pageWindow.page - 1); heading.current?.focus() }} onNext={() => void more()} />
      </>}
      <p className="activity-scope">{periodLabel(value.since)} – {periodLabel(value.as_of)}<span>Within your workspace’s activity retention</span></p>
      <details className="admin-activity-about"><summary>What’s included in the log and export?</summary><p>The JSON download includes the selected period and event type, up to 1,000 events and 8 MiB. It contains member and review IDs, event results and recorded decision changes. Source text, review titles, matched values, replacements, comments and Keep reasons are excluded. Review names on this page come from documents you can access.</p></details>
    </>}
  </section>
}
