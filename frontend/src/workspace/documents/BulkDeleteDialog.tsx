import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { Trash2 } from 'lucide-react'

export function BulkDeleteDialog({ count, pending, onCancel, onConfirm }: {
  count: number; pending: boolean; onCancel: () => void; onConfirm: () => void
}) {
  return <AlertDialog.Root open onOpenChange={(open) => { if (!open && !pending) onCancel() }}>
    <AlertDialog.Portal><AlertDialog.Overlay className="document-delete-overlay" />
      <AlertDialog.Content className="document-delete-dialog" onEscapeKeyDown={(event) => { if (pending) event.preventDefault() }}>
        <span className="document-delete-icon"><Trash2 size={22} aria-hidden="true" /></span>
        <AlertDialog.Title>Delete {count} selected {count === 1 ? 'review' : 'reviews'}?</AlertDialog.Title>
        <AlertDialog.Description>Access ends immediately and stored content is removed. These reviews cannot be restored. Only reviews you own can be deleted; each result will be shown.</AlertDialog.Description>
        <div className="document-dialog-actions"><AlertDialog.Cancel asChild><button type="button" disabled={pending}>Keep reviews</button></AlertDialog.Cancel>
          <button className="document-confirm-delete" type="button" disabled={pending} onClick={onConfirm}>{pending ? 'Deleting…' : 'Delete selected reviews'}</button>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>
}
