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
  const message = recovery.loading ? 'Checking for a working draft…'
    : recovery.phase === 'saving' ? 'Backing up your draft…'
    : recovery.error ? 'Backup needs attention'
    : recovery.protected && recovery.savedAt
      ? `Draft backed up at ${new Date(recovery.savedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      : dirty ? 'Changes waiting for backup' : 'Autosave ready'
  return (
    <Dialog.Root>
      <div className={cn('autosave-status', recovery.error && 'is-error')}>
        <div className="autosave-message">
          <span role="status">
            {recovery.loading || recovery.phase === 'saving' ? <LoadingMark small />
              : recovery.error ? <AlertCircle size={16} aria-hidden="true" />
              : recovery.protected ? <CloudCheck size={16} aria-hidden="true" />
              : <ShieldCheck size={16} aria-hidden="true" />}
            {message}
          </span>
          {recovery.error ? <p role="alert" className="autosave-error">
            {recovery.error} Your current edits are kept in this tab.
          </p> : recovery.recoveredAt && <small className="autosave-restored">Working draft recovered</small>}
        </div>
        <div className="autosave-actions">
          {recovery.error && <button type="button" disabled={recovery.loading || recovery.phase === 'saving'} onClick={recovery.retry}>
            <RotateCcw size={14} aria-hidden="true" /> Retry backup
          </button>}
          <Dialog.Trigger asChild>
            <button type="button" aria-label={`Manage working copies (${recovery.copies.length})`}>
              <Archive size={15} aria-hidden="true" /> Backups <span className="autosave-copy-count">{recovery.copies.length}</span>
            </button>
          </Dialog.Trigger>
        </div>
      </div>
      <DialogFrame title="Working copies" description="Each tab keeps its own backup. Recovering a copy first backs up your current edits." busy={recovery.loading || recovery.phase === 'saving'}>
        <div className="autosave-copy-manager">
          <div className="autosave-copy-heading"><strong>Saved copies</strong><span>{recovery.copies.length} available</span></div>
          {recovery.error && <p role="alert" className="autosave-manager-error">{recovery.error} Your current edits are kept in this tab.</p>}
          {recovery.copies.length === 0 ? <p className="autosave-empty">No other working copies. Your current draft stays in the editor.</p> : <ul className="autosave-copy-list" aria-label="Saved working copies">
            {recovery.copies.map((copy) => <li key={copy.id}>
              <FileClock size={18} aria-hidden="true" />
              <time dateTime={copy.updated_at}>
                <strong>{new Date(copy.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</strong>
                <span>{new Date(copy.updated_at).toLocaleTimeString()}</span>
              </time>
              <button type="button" aria-label={`Recover copy from ${new Date(copy.updated_at).toLocaleString()}`}
                disabled={recovery.loading || recovery.phase === 'saving'} onClick={() => void recovery.restore(copy.id)}>
                <RotateCcw size={14} aria-hidden="true" /> Recover
              </button>
              <AlertDialog.Root>
                <AlertDialog.Trigger asChild>
                  <button type="button" className="quiet-icon" aria-label={`Discard copy from ${new Date(copy.updated_at).toLocaleString()}`} disabled={recovery.loading || recovery.phase === 'saving'}>
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </AlertDialog.Trigger>
                <AlertDialog.Portal>
                  <AlertDialog.Overlay className="source-reload-overlay" />
                  <AlertDialog.Content className="source-reload-dialog">
                    <AlertDialog.Title>Discard this working copy?</AlertDialog.Title>
                    <AlertDialog.Description>
                      This removes the backup from {new Date(copy.updated_at).toLocaleString()}. Your current editor and saved source remain available.
                    </AlertDialog.Description>
                    <div className="source-conflict-actions">
                      <AlertDialog.Cancel asChild><button type="button">Keep copy</button></AlertDialog.Cancel>
                      <AlertDialog.Action asChild><button type="button" onClick={() => void recovery.discardCopy(copy.id)}>Discard working copy</button></AlertDialog.Action>
                    </div>
                  </AlertDialog.Content>
                </AlertDialog.Portal>
              </AlertDialog.Root>
            </li>)}
          </ul>}
          <div className="dialog-actions">
            {!recovery.error && <span role="status">{recovery.protected && recovery.recoveredAt ? 'Working draft recovered and backed up' : message}</span>}
            <Dialog.Close asChild><button type="button" disabled={recovery.loading || recovery.phase === 'saving'}>Done</button></Dialog.Close>
          </div>
        </div>
      </DialogFrame>
    </Dialog.Root>
  )
}
