import { CloudCheck, RotateCcw, ShieldCheck } from 'lucide-react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import type { ProtectedDraftController } from './useProtectedDraft'
import './recovery.css'
import '../review/source-recovery.css'
import { LoadingMark } from '../loading/LoadingMark'

export function AutosaveStatus({ recovery, dirty }: {
  recovery: ProtectedDraftController
  dirty: boolean
}) {
  const message = recovery.loading ? 'Checking for a working draft…'
    : recovery.phase === 'saving' ? 'Backing up your draft…'
    : recovery.protected && recovery.savedAt
      ? `Draft backed up at ${new Date(recovery.savedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      : dirty ? 'Changes waiting for backup' : 'Autosave ready'
  return (
    <div className="autosave-status">
      <span role="status">
        {recovery.loading || recovery.phase === 'saving' ? <LoadingMark small />
          : recovery.protected ? <CloudCheck size={15} aria-hidden="true" />
          : <ShieldCheck size={15} aria-hidden="true" />}
        {message}
      </span>
      {recovery.recoveredAt && <span className="autosave-restored">Working draft recovered</span>}
      {recovery.error && <div role="alert" className="autosave-error">
        <span>{recovery.error} Your current edits are kept here.</span>
        <button type="button" onClick={recovery.retry}>
          <RotateCcw size={13} aria-hidden="true" /> Retry backup
        </button>
      </div>}
      {recovery.copies.length > 0 && <details className="autosave-copies">
        <summary>Other working copies ({recovery.copies.length})</summary>
        <p>Each tab keeps a separate backup. Recovering a copy keeps your current backup.</p>
        {recovery.copies.map((copy) => <div key={copy.id}>
          <button type="button"
          disabled={recovery.loading || recovery.phase === 'saving'}
          onClick={() => void recovery.restore(copy.id)}>
          Recover copy from {new Date(copy.updated_at).toLocaleString()}
          </button>
          <AlertDialog.Root>
            <AlertDialog.Trigger asChild><button type="button">Discard copy</button></AlertDialog.Trigger>
            <AlertDialog.Portal>
              <AlertDialog.Overlay className="source-reload-overlay" />
              <AlertDialog.Content className="source-reload-dialog">
                <AlertDialog.Title>Discard this working copy?</AlertDialog.Title>
                <AlertDialog.Description>
                  This removes the selected recovery backup. Your current editor and saved source remain available.
                </AlertDialog.Description>
                <div className="source-conflict-actions">
                  <AlertDialog.Cancel asChild><button type="button">Keep copy</button></AlertDialog.Cancel>
                  <AlertDialog.Action asChild><button type="button" onClick={() => void recovery.discardCopy(copy.id)}>Discard working copy</button></AlertDialog.Action>
                </div>
              </AlertDialog.Content>
            </AlertDialog.Portal>
          </AlertDialog.Root>
        </div>)}
      </details>}
    </div>
  )
}
