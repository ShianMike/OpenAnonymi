import { AlertCircle, Archive, CloudCheck, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import * as Dialog from '@radix-ui/react-dialog'
import type { ProtectedDraftController } from './useProtectedDraft'
import { StudioDialog } from '../review/studio/StudioControls'
import { cn } from '../ui/cn'
import './recovery.css'
import '../review/source-recovery.css'
import { LoadingMark } from '../loading/LoadingMark'
import { LoadingState } from '../loading/LoadingState'

export function AutosaveStatus({ recovery, dirty }: {
  recovery: ProtectedDraftController
  dirty: boolean
}) {
  const full = recovery.errorCode === 'recovery_limit'
  const busy = recovery.loading || recovery.phase === 'saving'
  const errorHelp = full
    ? 'Your edits are still in this tab. Save your work, or delete an older backup to make room.'
    : 'Your edits are still in this tab. Try again, or save your work before leaving.'
  const message = recovery.loading ? 'Checking your backups…'
    : recovery.phase === 'saving' ? 'Backing up your draft…'
    : recovery.error ? full ? 'Backup space is full' : 'We couldn’t update your backups'
    : recovery.protected && recovery.savedAt
      ? `Draft backed up at ${new Date(recovery.savedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      : dirty ? 'Waiting for backup' : 'Autosave ready'
  return (
    <Dialog.Root>
      <div className={cn('autosave-status', recovery.error && 'is-error', full && 'is-full')}>
        <div className="autosave-message">
          <span role="status">
            {recovery.loading || recovery.phase === 'saving' ? <LoadingMark small />
              : full ? <Archive size={16} aria-hidden="true" />
              : recovery.error ? <AlertCircle size={16} aria-hidden="true" />
              : recovery.protected ? <CloudCheck size={16} aria-hidden="true" />
              : <ShieldCheck size={16} aria-hidden="true" />}
            {message}
          </span>
          {recovery.error ? <>
            <p role="alert" className="autosave-error">{errorHelp}</p>
            {!full && <details className="autosave-error-details"><summary>What happened?</summary><p>{recovery.error}</p></details>}
          </> : null}
        </div>
        <div className="autosave-actions">
          {recovery.error && (!full || recovery.copies.length === 0) && <button type="button" disabled={busy} onClick={recovery.retry}>
            <RotateCcw size={14} aria-hidden="true" /> Retry backup
          </button>}
          <Dialog.Trigger asChild>
            <button type="button" className={cn(full && 'autosave-manage')} aria-label={`Manage backups (${recovery.copies.length})`}>
              <Archive size={15} aria-hidden="true" /> {recovery.error ? 'Manage backups' : 'Backups'} <span className="autosave-copy-count">{recovery.copies.length}</span>
            </button>
          </Dialog.Trigger>
        </div>
      </div>
      <StudioDialog className="studio-backups-dialog" title="Draft backups" description="Recover an earlier working draft of this review." busy={busy}>
        <div className="studio-dialog-body autosave-copy-manager">
          <div className="autosave-preservation"><ShieldCheck size={18} aria-hidden="true" /><div><strong>Your current edits come first</strong><p>Restoring requires a backup of your current edits. Your saved review changes only when you save a revision.</p></div></div>
          {recovery.recoveredAt && <p className="autosave-restore-history">This draft was restored from a backup saved on <time dateTime={recovery.recoveredAt}>{new Date(recovery.recoveredAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time>.</p>}
          {recovery.error && <p role="alert" className={cn('autosave-manager-error', full && 'is-full')}>{full ? 'Delete a backup you no longer need, then retry. Your text in the editor won’t change.' : `${recovery.error} Your edits are still in this tab.`}</p>}
          <div className="autosave-copy-heading"><strong>Available drafts</strong><span>{recovery.loading ? 'Checking…' : `${recovery.copies.length} saved`}</span></div>
          {recovery.loading ? <LoadingState compact label="Checking your backups…" /> : recovery.copies.length === 0 ? <div className="autosave-empty"><Archive size={24} strokeWidth={1.4} aria-hidden="true" /><h3>No earlier drafts yet</h3><p>Backups appear here as you work. Your current text stays in the editor.</p></div> : <ul className="autosave-copy-list" aria-label="Saved backups">
            {recovery.copies.map((copy) => <li key={copy.id}>
              <div className="autosave-copy-date"><time dateTime={copy.updated_at}>
                <strong>{new Date(copy.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</strong>
                <span>{new Date(copy.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </time><small>Expires <time dateTime={copy.expires_at}>{new Date(copy.expires_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</time></small></div>
              <button type="button" aria-label={`Restore backup from ${new Date(copy.updated_at).toLocaleString()}`}
                disabled={busy} onClick={() => void recovery.restore(copy.id)}>
                <RotateCcw size={14} aria-hidden="true" /> Restore
              </button>
              <AlertDialog.Root>
                <AlertDialog.Trigger asChild>
                  <button type="button" className="quiet-icon" aria-label={`Delete backup from ${new Date(copy.updated_at).toLocaleString()}`} disabled={busy}>
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </AlertDialog.Trigger>
                <AlertDialog.Portal>
                  <AlertDialog.Overlay className="studio-overlay" />
                  <AlertDialog.Content className="studio studio-dialog studio-discard-dialog">
                    <AlertDialog.Title>Delete this backup?</AlertDialog.Title>
                    <AlertDialog.Description>
                      This permanently deletes the backup from {new Date(copy.updated_at).toLocaleString()}. Your current text and saved review won’t change.
                    </AlertDialog.Description>
                    <div className="source-conflict-actions">
                      <AlertDialog.Cancel asChild><button type="button">Keep backup</button></AlertDialog.Cancel>
                      <AlertDialog.Action asChild><button type="button" className="confirm-danger" onClick={() => void recovery.discardCopy(copy.id)}>Delete backup</button></AlertDialog.Action>
                    </div>
                  </AlertDialog.Content>
                </AlertDialog.Portal>
              </AlertDialog.Root>
            </li>)}
          </ul>}
        </div>
          <footer className="studio-dialog-footer autosave-manager-footer">
            {recovery.error ? <button type="button" disabled={busy} onClick={recovery.retry}><RotateCcw size={14} aria-hidden="true" /> Retry backup</button>
              : <span role="status">{recovery.protected && recovery.recoveredAt ? 'Restored text is backed up' : message}</span>}
            <Dialog.Close asChild><button type="button" disabled={busy}>Done</button></Dialog.Close>
          </footer>
      </StudioDialog>
    </Dialog.Root>
  )
}
