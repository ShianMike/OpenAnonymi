import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { Trash2 } from 'lucide-react'
import type { DocumentIndexView } from '../../api/client'
import { documentLabel } from './documentPresentation'

export function DocumentDeleteDialog({
  item,
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  item: DocumentIndexView
  pending: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <AlertDialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !pending) onCancel()
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="document-delete-overlay" />
        <AlertDialog.Content
          className="document-delete-dialog"
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault()
          }}
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          <span className="document-delete-icon">
            <Trash2 size={22} aria-hidden="true" />
          </span>
          <AlertDialog.Title>Delete this review?</AlertDialog.Title>
          <p className="document-delete-name">{documentLabel(item)}</p>
          <AlertDialog.Description>
            Access ends immediately and stored content is removed by cleanup. This review cannot be restored.
          </AlertDialog.Description>
          {error && <p role="alert">{error}</p>}
          <div className="document-dialog-actions">
            <AlertDialog.Cancel asChild>
              <button type="button" disabled={pending}>
                Keep review
              </button>
            </AlertDialog.Cancel>
            <button className="document-confirm-delete" type="button" onClick={onConfirm} disabled={pending}>
              {pending ? 'Deleting…' : 'Delete review'}
            </button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
