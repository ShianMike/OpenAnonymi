import { useEffect, useRef, useState, type RefObject } from 'react'
import { useBlocker } from 'react-router-dom'

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
  const stayRef = useRef<HTMLButtonElement>(null)
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

  useEffect(() => {
    if (blocker.state === 'blocked') stayRef.current?.focus()
  }, [blocker.state])

  if (blocker.state !== 'blocked') return null
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
    <div className="unsaved-navigation surface-panel" role="alert">
      <strong>{saving ? 'Decisions are saving' : 'Unsaved changes'}</strong>
      <p>{saving ? 'Wait for your decisions and reviewed output to finish saving before leaving.' : onSaveAndLeave ? 'Back up your current edits before leaving, or discard this working copy.'
        : 'Leaving this page will discard your unsaved text and settings.'}</p>
      <button
        ref={stayRef}
        type="button"
        disabled={pending}
        onClick={() => {
          blocker.reset()
          onStay?.()
          requestAnimationFrame(() => document.getElementById(focusBackId)?.focus())
        }}
      >
        Stay and keep editing
      </button>{' '}
      {saving && <button type="button" className="button-primary" disabled={pending}
        onClick={() => void waitAndLeave()}>{pending ? 'Waiting for saves…' : 'Wait for saves and leave'}</button>}
      {!saving && onSaveAndLeave && <button type="button" className="button-primary" disabled={pending}
        onClick={() => void leave(true)}>{pending ? 'Backing up…' : 'Back up and leave'}</button>}{' '}
      {!saving && <button type="button" disabled={pending} onClick={() => void leave(false)}>
        Discard edits and leave
      </button>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
