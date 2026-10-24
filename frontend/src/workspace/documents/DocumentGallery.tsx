import { ArrowUpRight, Check, Clock3, Pin, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView, DocumentPreferenceRequest } from '../../api/client'
import { StatusBadge } from '../../ui/StatusBadge'
import { reviewNextStep } from '../../resume/reviewQueue'
import { DocumentActions } from './DocumentActions'
import { documentLabel, relativeEdit, retention } from './documentPresentation'

export function DocumentGallery({ items, workspaceId, search, now, onDelete, selected, selecting, pending,
  preferencePending, onSelect, onPreference, onRenew }: {
  items: DocumentIndexView[]; workspaceId: string; search: string; now: number
  onDelete: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
  selected: Set<string>; selecting: boolean; pending: boolean; preferencePending: Set<string>
  onSelect: (id: string, value: boolean) => void
  onPreference: (item: DocumentIndexView, value: DocumentPreferenceRequest) => void
  onRenew: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
}) {
  return <ul id="document-gallery" className="document-gallery" aria-label="Documents">
    {items.map(item => {
      const lifetime = retention(item, now)
      const unavailable = lifetime.expired || item.status === 'deleted' || !item.current_revision_id
      const title = unavailable ? 'Expired review' : documentLabel(item)
      const count = item.finding_count
      const decided = Math.min(count, item.decided_count)
      const content = <>
        <h2>{title}</h2>
        <span className="document-card-owner">{item.is_owner ? 'Your review' : 'Shared with you'}
          {item.pinned && !unavailable && <Pin size={12} aria-label="Pinned" />}{item.favorite && !unavailable && <Star size={12} aria-label="Favorite" />}
        </span>
        <div id={`document-${item.id}-review`} className="document-card-review">
          <StatusBadge status={unavailable ? 'expired' : item.status} />
          <p>{unavailable ? 'Content is no longer available' : reviewNextStep(item)}</p>
          {!unavailable && count > 0 && !['draft', 'scanning', 'failed'].includes(item.status) &&
            <span className="document-progress"><progress max={count} value={decided} aria-label={`Findings reviewed in ${title}`} /><span>{decided} of {count} reviewed</span></span>}
        </div>
        {!unavailable && <span className="document-card-open" aria-hidden={selecting || undefined}>{['ready', 'exported'].includes(item.status) ? 'Open review' : 'Continue review'}<ArrowUpRight size={14} aria-hidden="true" /></span>}
      </>
      return <li key={item.id} className="document-card" data-selecting={selecting || undefined} data-selected={selecting && selected.has(item.id) || undefined} data-unavailable={unavailable || undefined}>
        {selecting ? <>
          <input className="document-card-selector" type="checkbox" aria-label={`Select ${title}`} checked={selected.has(item.id)}
            aria-describedby={`document-${item.id}-review document-selection-help`}
            disabled={pending || (!selected.has(item.id) && selected.size >= 50)} onChange={event => onSelect(item.id, event.target.checked)} />
          <span className="document-selection-indicator" aria-hidden="true"><Check size={13} /></span>
        </> : <div className="document-card-header">
          <DocumentActions item={unavailable ? { ...item, title: null, status: 'expired' } : item} workspaceId={workspaceId} search={search} unavailable={unavailable}
            onDelete={onDelete} preferencePending={pending || preferencePending.has(item.id)} onPreference={onPreference} onRenew={onRenew} />
        </div>}
        {selecting || unavailable ? <div className="document-card-body">{content}</div> : <Link className="document-card-body" to={`/documents/${item.id}/edit`} state={{ documentsSearch: search }} aria-label={`Open ${title}`} aria-describedby={`document-${item.id}-review`}>{content}</Link>}
        <div className="document-card-footer">
          <time dateTime={item.updated_at} title={`Updated ${new Date(item.updated_at).toLocaleString()}`}>{relativeEdit(item.updated_at, now)}</time>
          <span data-urgent={lifetime.urgent || undefined} title={`Retention ends ${new Date(item.expires_at).toLocaleString()}`}><Clock3 size={12} aria-hidden="true" />{lifetime.label}</span>
        </div>
      </li>
    })}
  </ul>
}
