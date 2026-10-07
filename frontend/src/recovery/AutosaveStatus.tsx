import { AlertCircle, Archive, CloudCheck, FileClock, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import * as Dialog from '@radix-ui/react-dialog'
import type { ProtectedDraftController } from './useProtectedDraft'
import { DialogFrame } from '../ui/WorkspaceControls'
import { cn } from '../ui/cn'
import './recovery.css'
import '../review/source-recovery.css'
import { LoadingMark } from '../loading/LoadingMark'

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
      : dirty ? 'Changes waiting for backup' : 'Autosave ready'
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
          </> : recovery.recoveredAt && <small className="autosave-restored">Text restored from a backup</small>}
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
      <DialogFrame title="Draft backups" description="Restore your text and settings from a backup. Your current edits must be backed up first." busy={busy}>
        <div className="autosave-copy-manager">
          <div className="autosave-copy-heading"><strong>Earlier backups</strong><span>{recovery.copies.length} available</span></div>
          {recovery.error && <p role="alert" className={cn('autosave-manager-error', full && 'is-full')}>{full ? 'Delete a backup you no longer need, then retry. Your text in the editor won’t change.' : `${recovery.error} Your edits are still in this tab.`}</p>}
          {recovery.copies.length === 0 ? <p className="autosave-empty">No earlier backups for this review. Your current text stays in the editor.</p> : <ul className="autosave-copy-list" aria-label="Saved backups">
            {recovery.copies.map((copy) => <li key={copy.id}>
              <FileClock size={18} aria-hidden="true" />
              <time dateTime={copy.updated_at}>
                <strong>{new Date(copy.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</strong>
                <span>{new Date(copy.updated_at).toLocaleTimeString()}</span>
              </time>
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
                  <AlertDialog.Overlay className="source-reload-overlay" />
                  <AlertDialog.Content className="source-reload-dialog">
                    <AlertDialog.Title>Delete this backup?</AlertDialog.Title>
                    <AlertDialog.Description>
                      This permanently deletes the backup from {new Date(copy.updated_at).toLocaleString()}. Your current text and saved review won’t change.
                    </AlertDialog.Description>
                    <div className="source-conflict-actions">
                      <AlertDialog.Cancel asChild><button type="button">Keep backup</button></AlertDialog.Cancel>
                      <AlertDialog.Action asChild><button type="button" onClick={() => void recovery.discardCopy(copy.id)}>Delete backup</button></AlertDialog.Action>
                    </div>
                  </AlertDialog.Content>
                </AlertDialog.Portal>
              </AlertDialog.Root>
            </li>)}
          </ul>}
          <div className="dialog-actions">
            {recovery.error ? <button type="button" disabled={busy} onClick={recovery.retry}><RotateCcw size={14} aria-hidden="true" /> Retry backup</button>
              : <span role="status">{recovery.protected && recovery.recoveredAt ? 'Restored text is backed up' : message}</span>}
            <Dialog.Close asChild><button type="button" disabled={busy}>Done</button></Dialog.Close>
          </div>
        </div>
      </DialogFrame>
    </Dialog.Root>
  )
}
