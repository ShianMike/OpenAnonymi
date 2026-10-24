import { useEffect, type ReactNode, type RefObject } from 'react'
import { useBlocker } from 'react-router-dom'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { cn } from '../../ui/cn'

export function SettingsConfirmation({ open, title, description, children, pending, pendingLabel = 'Saving…', error, confirmLabel, danger, onCancel, onConfirm, returnFocus, dirty = false, navigationWarning }: {
  open: boolean; title: string; description: string; children?: ReactNode; pending: boolean; error?: string | null
  confirmLabel: string; pendingLabel?: string; danger?: boolean; onCancel: () => void; onConfirm: () => void; returnFocus: RefObject<HTMLElement | null>
  dirty?: boolean; navigationWarning?: { title: string; description: string; leaveLabel: string }
}) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => (dirty || pending) &&
    (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search))
  const leaving = blocker.state === 'blocked'
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, pending])
  function cancel() { if (leaving) blocker.reset?.(); else onCancel() }
  const navigationTitle = pending ? 'Wait for this change to finish' : !dirty ? 'Continue from settings?' : navigationWarning?.title ?? 'Discard unsaved changes?'
  const navigationDescription = pending ? 'Your request is still running. Stay on this page until it finishes.' : !dirty ? 'Your change has been saved. You can continue to the page you selected.' : navigationWarning?.description ?? 'Your edits haven’t been saved. Stay here to keep editing, or discard them and leave.'
  return <AlertDialog.Root open={open || leaving} onOpenChange={value => { if (!value && (!pending || leaving)) cancel() }}><AlertDialog.Portal><AlertDialog.Overlay className="workspace-dialog-overlay" /><AlertDialog.Content className="workspace-dialog settings-confirmation" aria-busy={pending}
    onEscapeKeyDown={event => { if (pending && !leaving) event.preventDefault() }} onCloseAutoFocus={event => {
      event.preventDefault()
      const target = returnFocus.current
      if (target?.isConnected && !target.matches(':disabled')) target.focus()
      else document.querySelector<HTMLElement>('.settings-content-header h2')?.focus({ preventScroll: true })
    }}>
    <AlertDialog.Title>{leaving ? navigationTitle : title}</AlertDialog.Title><AlertDialog.Description>{leaving ? navigationDescription : description}</AlertDialog.Description>
    {!leaving && children}
    {!leaving && error && <InlineNotice error title="The request couldn’t be completed">{error}</InlineNotice>}
    <footer><AlertDialog.Cancel className="settings-button" disabled={pending && !leaving}>{leaving ? 'Stay here' : 'Cancel'}</AlertDialog.Cancel>{(!leaving || !pending) && <button type="button" className={cn('settings-button', (leaving ? dirty : danger) ? 'settings-danger-solid' : 'settings-primary')} disabled={pending} onClick={leaving ? () => blocker.proceed?.() : onConfirm}>{pending ? pendingLabel : leaving ? !dirty ? 'Continue' : navigationWarning?.leaveLabel ?? 'Discard and leave' : confirmLabel}</button>}</footer>
  </AlertDialog.Content></AlertDialog.Portal></AlertDialog.Root>
}
