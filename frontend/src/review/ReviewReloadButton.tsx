import * as AlertDialog from '@radix-ui/react-alert-dialog'
import type { ReviewController } from './useReviewController'
import './source-recovery.css'

export function ReviewReloadButton({ review }: { review: ReviewController }) {
  if (!review.dirty) {
    return (
      <button type="button" onClick={review.reloadSaved} disabled={review.actionPending}>
        Reload saved
      </button>
    )
  }
  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger asChild>
        <button type="button" disabled={review.actionPending}>Discard edits and reload saved</button>
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="source-reload-overlay" />
        <AlertDialog.Content className="source-reload-dialog">
          <AlertDialog.Title>Discard your unsaved edits?</AlertDialog.Title>
          <AlertDialog.Description>
            Your editor text will be replaced with the latest saved version. Copy it first if
            you want to keep a backup.
          </AlertDialog.Description>
          <div className="source-conflict-actions">
            <AlertDialog.Cancel asChild>
              <button type="button">Keep editing</button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button type="button" onClick={review.reloadSaved}>Discard and reload</button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
