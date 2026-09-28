import { useEffect, useRef, type RefObject } from 'react'
import { useBlocker } from 'react-router-dom'

export function UnsavedNavigationPrompt({
  when, focusBackId, allowNavigationRef, onDirtyChange,
}: {
  when: boolean
  focusBackId: string
  allowNavigationRef?: RefObject<boolean>
  onDirtyChange?: (dirty: boolean) => void
}) {
  const stayRef = useRef<HTMLButtonElement>(null)
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    when && !allowNavigationRef?.current && (
      currentLocation.pathname !== nextLocation.pathname ||
      currentLocation.search !== nextLocation.search
    ),
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
  return (
    <div className="unsaved-navigation surface-panel" role="alert">
      <strong>Unsaved changes</strong>
      <p>Leaving this page will discard your unsaved text and settings.</p>
      <button ref={stayRef} type="button" onClick={() => {
        blocker.reset()
        requestAnimationFrame(() => document.getElementById(focusBackId)?.focus())
      }}>Stay and keep editing</button>{' '}
      <button type="button" onClick={() => blocker.proceed()}>Discard edits and leave</button>
    </div>
  )
}
