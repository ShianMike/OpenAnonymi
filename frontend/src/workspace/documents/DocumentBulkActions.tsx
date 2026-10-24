import { useRef } from 'react'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { ChevronDown, Pin, Star, Trash2, X } from 'lucide-react'
import type { BulkDocumentsRequest, BulkDocumentsView, DocumentIndexView } from '../../api/client'
import { documentLabel } from './documentPresentation'

export function DocumentBulkActions({ count, pending, canDelete, canUpdate, onApply }: {
  count: number; pending: boolean; canDelete: boolean; canUpdate: boolean
  onApply: (action: BulkDocumentsRequest['action'], trigger: HTMLButtonElement | null) => void
}) {
  const trigger = useRef<HTMLButtonElement>(null)
  const openingConfirmation = useRef(false)
  return <Menu.Root modal={false}>
    <Menu.Trigger ref={trigger} className="document-selection-actions" disabled={pending || !count} aria-label="Actions for selected documents">
      {pending ? 'Applying…' : 'Actions'}<ChevronDown size={14} aria-hidden="true" />
    </Menu.Trigger>
    <Menu.Portal><Menu.Content className="document-action-menu" sideOffset={6} align="end" collisionPadding={12}
      onCloseAutoFocus={event => { if (openingConfirmation.current) { event.preventDefault(); openingConfirmation.current = false } }}>
      <Menu.Label className="document-menu-label">Apply to {count} {count === 1 ? 'document' : 'documents'}</Menu.Label>
      <Menu.Item disabled={!canUpdate} onSelect={() => onApply('favorite', trigger.current)}><Star size={15} aria-hidden="true" />Add to favorites</Menu.Item>
      <Menu.Item disabled={!canUpdate} onSelect={() => onApply('unfavorite', trigger.current)}><Star size={15} aria-hidden="true" />Remove from favorites</Menu.Item>
      <Menu.Separator className="document-menu-separator" />
      <Menu.Item disabled={!canUpdate} onSelect={() => onApply('pin', trigger.current)}><Pin size={15} aria-hidden="true" />Pin to top</Menu.Item>
      <Menu.Item disabled={!canUpdate} onSelect={() => onApply('unpin', trigger.current)}><Pin size={15} aria-hidden="true" />Unpin documents</Menu.Item>
      <Menu.Separator className="document-menu-separator" />
      <Menu.Item className="document-menu-delete" disabled={!canDelete} onSelect={() => {
        openingConfirmation.current = true
        onApply('delete', trigger.current)
      }}><Trash2 size={15} aria-hidden="true" />Delete selected</Menu.Item>
    </Menu.Content></Menu.Portal>
  </Menu.Root>
}

export function DocumentBulkResults({ results, onDismiss }: {
  results: { value: BulkDocumentsView; items: DocumentIndexView[] }; onDismiss: () => void
}) {
  return <div className="document-bulk-results" role="status">
    <details><summary>Results for {results.value.outcomes.length} selected {results.value.outcomes.length === 1 ? 'document' : 'documents'}</summary>
      <ul>{results.value.outcomes.map(item => <li key={item.document_id}>
        <strong>{documentLabel(results.items.find(row => row.id === item.document_id) ?? { title: null, status: 'draft' } as DocumentIndexView)}</strong>
        <span>{({ updated: 'Preferences saved', deleted: 'Review deleted', not_found: 'Unavailable or access changed', unavailable: 'Retention ended; no change made', session_ended: 'Session ended; no change made' })[item.outcome]}</span>
      </li>)}</ul>
    </details>
    <button type="button" className="document-icon-button" onClick={onDismiss} aria-label="Dismiss action results"><X size={14} /></button>
  </div>
}
