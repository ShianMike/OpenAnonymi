import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowRight, CalendarClock, Check, ShieldCheck } from 'lucide-react'
import { ApiRequestError, getRetention, renewRetention, type RetentionView } from '../api/client'
import { StudioDialog, StudioSelect } from '../review/studio/StudioControls'
import { LoadingState } from '../loading/LoadingState'
import './retention.css'

export function RetentionDialog({ documentId, csrf, returnFocus, onClose, onSaved }: {
  documentId: string; csrf: string; returnFocus: HTMLElement | null; onClose: () => void; onSaved: (value: RetentionView) => void
}) {
  const [value, setValue] = useState<RetentionView | null>(null)
  const [days, setDays] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    const controller = new AbortController()
    getRetention(documentId, controller.signal).then(view => {
      if (controller.signal.aborted) return
      setValue(view); setDays(view.maximum_days)
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      setUnavailable(cause instanceof ApiRequestError && [401, 403, 404, 410].includes(cause.status))
      setError(cause instanceof Error ? cause.message : 'Retention could not be loaded.')
    })
    return () => { active.current = false; controller.abort() }
  }, [documentId, attempt])
  const options = value ? Array.from({ length: value.maximum_days }, (_, i) => i + 1)
    .filter(day => Date.parse(value.current_time) + day * 86_400_000 > Date.parse(value.expires_at)) : []
  const proposedExpiry = value && new Date(Date.parse(value.current_time) + days * 86_400_000)
  async function save() {
    if (!value || pending || !options.includes(days) || unavailable) return
    setPending(true); setError(null)
    try {
      const result = await renewRetention(documentId, value.expires_at, days, csrf)
      if (active.current) onSaved(result)
    } catch (cause) {
      if (active.current) {
        const stale = cause instanceof ApiRequestError && cause.status === 409
        if (cause instanceof ApiRequestError && [401, 403, 404, 410].includes(cause.status)) { setValue(null); setUnavailable(true) }
        if (stale) { setValue(null); setAttempt(current => current + 1) }
        setError(cause instanceof Error ? cause.message : 'Retention could not be renewed.')
      }
    } finally { if (active.current) setPending(false) }
  }
  return <Dialog.Root open onOpenChange={open => { if (!open && !pending) onClose() }}>
    <StudioDialog title="Extend review availability" description="Choose how long to keep this review within your workspace’s retention limit."
      className="studio-retention-dialog" busy={pending}
      onCloseAutoFocus={event => { event.preventDefault(); if (returnFocus?.isConnected) returnFocus.focus() }}>
      <div className="studio-dialog-body">
      {!value && !error && <LoadingState compact label="Checking review availability…" description="Loading the current expiry and workspace limit." />}
      {value && <>
        <div className="retention-dates">
          <div className="retention-date"><span>Available until</span><time dateTime={value.expires_at}>{new Date(value.expires_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}<small>{new Date(value.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></time></div>
          {options.length > 0 && proposedExpiry && <><ArrowRight size={17} aria-hidden="true" /><div className="retention-date is-proposed"><span>New expiry</span><time dateTime={proposedExpiry.toISOString()}>{proposedExpiry.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}<small>{proposedExpiry.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></time></div></>}
        </div>
        {options.length ? <>
          <label className="field-label" htmlFor="renew-retention-days">Keep this review for</label>
          <StudioSelect id="renew-retention-days" value={days} disabled={pending} onValueChange={choice => setDays(Number(choice))}>
            {options.map(day => <option key={day} value={day}>{day} day{day === 1 ? '' : 's'} from now</option>)}
          </StudioSelect>
          <p className="field-note">Workspace limit: {value.maximum_days} day{value.maximum_days === 1 ? '' : 's'} from today.</p>
        </> : <div className="retention-limit"><Check size={18} aria-hidden="true" /><div><strong>You already have the longest available duration</strong><p>Check again closer to expiry to extend this review.</p></div></div>}
        <p className="retention-preserved"><ShieldCheck size={16} aria-hidden="true" /><span>Your source, decisions and confirmation stay as they are. Expired or deleted content cannot be renewed.</span></p>
      </>}
      {error && <div className="retention-error" role="alert"><CalendarClock size={18} aria-hidden="true" /><div><strong>{unavailable ? 'This review is no longer available to renew' : value ? 'We couldn’t extend review availability' : 'We couldn’t check review availability'}</strong><p>{error}</p></div></div>}
      </div>
      <footer className="studio-dialog-footer">
        <button type="button" disabled={pending} onClick={onClose}>Close</button>
        {!unavailable && !value && error && <button type="button" onClick={() => { setError(null); setAttempt(current => current + 1) }}>Check again</button>}
        {value && options.length > 0 && !unavailable && <button type="button" className="button-primary" disabled={pending} onClick={() => void save()}>{pending ? 'Extending…' : 'Extend availability'}</button>}
      </footer>
    </StudioDialog>
  </Dialog.Root>
}
