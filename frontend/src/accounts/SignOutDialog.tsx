import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { LogOut } from 'lucide-react'
import './auth.css'

/** Editors that can hold the unsaved work this prompt protects. */
const EDITOR = '#source-text, #source-file, #saved-source'

/** Shown only when signing out would discard unsaved editor work. */
export function SignOutDialog({
  open,
  pending,
  onStay,
  onConfirm,
}: {
  open: boolean
  pending: boolean
  onStay: () => void
  onConfirm: () => void
}) {
  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next && !pending) onStay()
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="auth-dialog-overlay" />
        <AlertDialog.Content
          className="auth-dialog"
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault()
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            document.querySelector<HTMLElement>(EDITOR)?.focus()
          }}
        >
          <span className="auth-dialog-icon">
            <LogOut size={20} strokeWidth={1.8} aria-hidden="true" />
          </span>
          <AlertDialog.Title>Unsaved changes</AlertDialog.Title>
          <AlertDialog.Description>
            Signing out will discard your unsaved text and settings.
          </AlertDialog.Description>
          <div className="auth-dialog-actions">
            <AlertDialog.Cancel asChild>
              <button type="button" disabled={pending}>
                Stay and keep editing
              </button>
            </AlertDialog.Cancel>
            <button type="button" className="auth-dialog-danger" disabled={pending} onClick={onConfirm}>
              Discard edits and sign out
            </button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
