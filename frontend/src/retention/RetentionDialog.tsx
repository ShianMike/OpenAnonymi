import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Clock3 } from 'lucide-react'
import { ApiRequestError, getRetention, renewRetention, type RetentionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
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
    <Dialog.Portal><Dialog.Overlay className="retention-overlay" /><Dialog.Content className="retention-dialog"
      onCloseAutoFocus={event => { event.preventDefault(); if (returnFocus?.isConnected) returnFocus.focus() }}
      onEscapeKeyDown={event => { if (pending) event.preventDefault() }}
      onPointerDownOutside={event => { if (pending) event.preventDefault() }}>
      <Clock3 size={24} aria-hidden="true" />
      <Dialog.Title>Renew retention</Dialog.Title>
      <Dialog.Description>Keep this saved review longer under the current workspace policy. Expired or deleted content cannot be renewed.</Dialog.Description>
      {!value && !error && <p role="status">Checking the current retention date…</p>}
      {value && <>
        <p>Current expiry: <strong>{new Date(value.expires_at).toLocaleString()}</strong></p>
        {options.length ? <>
          <label htmlFor="renew-retention-days">Keep from now</label>
          <GlassSelect id="renew-retention-days" value={days} disabled={pending} onValueChange={choice => setDays(Number(choice))}>
            {options.map(day => <option key={day} value={day}>{day} day{day === 1 ? '' : 's'}</option>)}
          </GlassSelect>
          <p className="retention-proposed">New expiry: {new Date(Date.parse(value.current_time) + days * 86_400_000).toLocaleString()}</p>
        </> : <p>Your current date already covers the maximum duration allowed by this workspace. Check again closer to expiry.</p>}
        <p className="retention-proposed">Your source, decisions and confirmation are preserved.</p>
      </>}
      {error && <p role="alert">{error}</p>}
      <div className="retention-buttons">
        <button type="button" disabled={pending} onClick={onClose}>Close</button>
        {!unavailable && !value && error && <button type="button" onClick={() => { setError(null); setAttempt(current => current + 1) }}>Check again</button>}
        {value && options.length > 0 && !unavailable && <button type="button" className="button-primary" disabled={pending} onClick={() => void save()}>{pending ? 'Renewing…' : 'Renew retention'}</button>}
      </div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>
}
