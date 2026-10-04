import { X } from 'lucide-react'
import { GlassSelect } from '../../ui/GlassSelect'
import type { BulkDocumentsRequest, BulkDocumentsView, DocumentIndexView } from '../../api/client'
import { documentLabel } from './documentPresentation'

export function DocumentBulkActions({ count, action, pending, onAction, onApply, onClear, results, allVisibleSelected, hasVisible, onSelectVisible }: {
  count: number; action: BulkDocumentsRequest['action']; pending: boolean
  onAction: (value: BulkDocumentsRequest['action']) => void; onApply: () => void; onClear: () => void
  results: { value: BulkDocumentsView; items: DocumentIndexView[] } | null
  allVisibleSelected: boolean; hasVisible: boolean; onSelectVisible: (value: boolean) => void
}) {
  return <div className="document-bulk">
    <div className="document-bulk-controls" role="region" aria-label="Bulk document actions">
      <label className="document-select-visible"><input type="checkbox" checked={allVisibleSelected} disabled={pending || !hasVisible} onChange={(event) => onSelectVisible(event.target.checked)} /> Select visible</label>
      <span role="status">{count} selected <small>· Up to 50</small></span>
      <div><label className="sr-only" htmlFor="bulk-document-action">Bulk action</label>
        <GlassSelect id="bulk-document-action" value={action} disabled={pending} onValueChange={(value) => onAction(value as BulkDocumentsRequest['action'])}>
          <option value="favorite">Add favorites</option><option value="unfavorite">Remove favorites</option>
          <option value="pin">Pin reviews</option><option value="unpin">Unpin reviews</option><option value="delete">Delete reviews</option>
        </GlassSelect></div>
      <button type="button" disabled={pending || !count} onClick={onApply}>{pending ? 'Applying…' : 'Apply to selected'}</button>
      {count > 0 && <button type="button" disabled={pending} onClick={onClear} aria-label="Clear selection"><X size={15} aria-hidden="true" /> Clear</button>}
    </div>
    {results && <section className="document-bulk-results" aria-label="Bulk action results" aria-live="polite">
      <h2>Action results</h2><ul>{results.value.outcomes.map((item) => <li key={item.document_id}>
        <strong>{documentLabel(results.items.find((row) => row.id === item.document_id) ?? { title: null, status: 'draft' } as DocumentIndexView)}</strong>
        <span>{({ updated: 'Preferences saved', deleted: 'Review deleted', not_found: 'Review unavailable or access changed', unavailable: 'Retention ended; no change made', session_ended: 'Session ended; no change made' })[item.outcome]}</span>
      </li>)}</ul>
    </section>}
  </div>
}
