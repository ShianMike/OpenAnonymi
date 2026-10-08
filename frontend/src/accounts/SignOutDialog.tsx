import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { CircleAlert, LogOut } from 'lucide-react'
import { LoadingMark } from '../loading/LoadingMark'
import { cn } from '../ui/cn'
import './auth.css'

/** Editors that can hold the unsaved work this prompt protects. */
const EDITOR = '#source-text, #source-file, #saved-source'

/** Every sign-out asks first; unsaved editor work gets an explicit warning. */
export function SignOutDialog({
  open,
  pending,
  unsaved,
  error,
  onStay,
  onConfirm,
  restoreFocus,
}: {
  open: boolean
  pending: boolean
  unsaved: boolean
  error: string | null
  onStay: () => void
  onConfirm: () => void
  restoreFocus: () => void
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
          aria-busy={pending}
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault()
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            const editor = unsaved ? document.querySelector<HTMLElement>(EDITOR) : null
            if (editor) editor.focus()
            else restoreFocus()
          }}
        >
          <span className="auth-dialog-icon">
            <LogOut size={20} strokeWidth={1.8} aria-hidden="true" />
          </span>
          <AlertDialog.Title>{unsaved ? 'Unsaved changes' : 'Sign out of OpenAnonymi?'}</AlertDialog.Title>
          <AlertDialog.Description>
            {unsaved ? 'Signing out will discard your unsaved changes and selected files.'
              : 'Your saved reviews will be here when you return. You’ll need to sign in again to continue.'}
          </AlertDialog.Description>
          {error && <div className="signout-error" role="alert"><CircleAlert size={17} aria-hidden="true" /><span>{error}</span></div>}
          <div className="auth-dialog-actions">
            <AlertDialog.Cancel asChild>
              <button type="button" disabled={pending}>
                {unsaved ? 'Stay and keep editing' : 'Stay signed in'}
              </button>
            </AlertDialog.Cancel>
            <button type="button" className={cn('auth-dialog-confirm', unsaved ? 'auth-dialog-danger' : 'button-primary')} disabled={pending} onClick={onConfirm}>
              {pending && <LoadingMark small />}
              {pending ? 'Signing out…' : unsaved ? 'Discard edits and sign out' : 'Sign out'}
            </button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
