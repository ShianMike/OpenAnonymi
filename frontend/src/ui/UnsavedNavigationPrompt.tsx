import { useEffect, useRef, useState, type RefObject } from 'react'
import { useBlocker } from 'react-router-dom'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { ShieldCheck } from 'lucide-react'
import './workspace-controls.css'

export function UnsavedNavigationPrompt({
  when,
  focusBackId,
  allowNavigationRef,
  onDirtyChange,
  onStay,
  onSaveAndLeave,
  onDiscardAndLeave,
  saving = false,
  onWaitAndLeave,
}: {
  when: boolean
  focusBackId: string
  allowNavigationRef?: RefObject<boolean>
  onDirtyChange?: (dirty: boolean) => void
  onStay?: () => void
  onSaveAndLeave?: () => Promise<boolean>
  onDiscardAndLeave?: () => Promise<void>
  saving?: boolean
  onWaitAndLeave?: () => Promise<boolean>
}) {
  const restoreFocus = useRef(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      when &&
      !allowNavigationRef?.current &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  )

  useEffect(() => {
    onDirtyChange?.(when)
    return () => onDirtyChange?.(false)
  }, [when, onDirtyChange])

  useEffect(() => {
    if (!when) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [when])

  function stay() {
    restoreFocus.current = true
    setError(null)
    blocker.reset?.()
    onStay?.()
  }
  async function leave(save: boolean) {
    setPending(true)
    setError(null)
    try {
      if (save && onSaveAndLeave && !(await onSaveAndLeave())) {
        setError('The latest edits could not be backed up. Keep editing here or retry.')
        return
      }
      if (!save) await onDiscardAndLeave?.()
      blocker.proceed?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Your edits could not be backed up.')
    } finally { setPending(false) }
  }
  async function waitAndLeave() {
    setPending(true); setError(null)
    try {
      if (!(await onWaitAndLeave?.())) { setError('The decisions could not finish saving. Stay here and reload the saved review.'); return }
      blocker.proceed?.()
    } catch { setError('The decisions could not finish saving. Stay here and reload the saved review.') }
    finally { setPending(false) }
  }
  return (
    <AlertDialog.Root open={blocker.state === 'blocked'} onOpenChange={(open) => {
      if (!open && !pending) stay()
    }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="workspace-dialog-overlay" />
        <AlertDialog.Content className="unsaved-navigation workspace-dialog" aria-busy={pending}
          onEscapeKeyDown={(event) => { if (pending) event.preventDefault() }}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            if (restoreFocus.current) {
              restoreFocus.current = false
              requestAnimationFrame(() => document.getElementById(focusBackId)?.focus())
            }
          }}>
          <span className="panel-heading-icon"><ShieldCheck size={22} aria-hidden="true" /></span>
          <AlertDialog.Title>{saving ? 'Decisions are saving' : 'Unsaved changes'}</AlertDialog.Title>
          <AlertDialog.Description>{saving ? 'Wait for your decisions and reviewed output to finish saving before leaving.' : onSaveAndLeave ? 'Back up your current edits before leaving, or discard this working copy.'
            : 'Leaving this page will discard your unsaved text and settings.'}</AlertDialog.Description>
          {error && <p className="unsaved-navigation-error" role="alert">{error}</p>}
          <div className="unsaved-navigation-actions">
            <AlertDialog.Cancel asChild><button type="button" disabled={pending}>Stay and keep editing</button></AlertDialog.Cancel>
            {saving && <button type="button" className="button-primary" disabled={pending}
              onClick={() => void waitAndLeave()}>{pending ? 'Waiting for saves…' : 'Wait for saves and leave'}</button>}
            {!saving && onSaveAndLeave && <button type="button" className="button-primary" disabled={pending}
              onClick={() => void leave(true)}>{pending ? 'Backing up…' : 'Back up and leave'}</button>}
            {!saving && <button type="button" className="unsaved-navigation-discard" disabled={pending} onClick={() => void leave(false)}>Discard edits and leave</button>}
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
