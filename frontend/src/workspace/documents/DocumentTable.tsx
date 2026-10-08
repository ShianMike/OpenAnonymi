import { Check, Clock3, FileText, Pin, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView, DocumentPreferenceRequest } from '../../api/client'
import { StatusBadge } from '../../ui/StatusBadge'
import { DocumentActions } from './DocumentActions'
import { documentLabel, relativeEdit, retention, shortDate } from './documentPresentation'

function ReviewProgress({ item }: { item: DocumentIndexView }) {
  const count = item.finding_count
  const decided = Math.min(count, item.decided_count)
  if (item.status === 'expired' || item.status === 'deleted')
    return <span className="document-muted">Unavailable</span>
  if (item.status === 'draft') return <span className="document-progress-placeholder">Not checked yet</span>
  if (item.status === 'scanning') return <span className="document-progress-placeholder">Checking for details…</span>
  if (item.status === 'failed')
    return <span className="document-progress-placeholder">Try the check again</span>
  if (count === 0)
    return (
      <span className="document-progress-empty">
        <Check size={14} aria-hidden="true" /> No details flagged
      </span>
    )
  return (
    <div className={`document-progress ${decided === count ? 'is-decided' : ''}`}>
      <span className="document-progress-label">
        <strong>
          {decided}
          <span> of {count}</span>
        </strong>
        <span>checked</span>
      </span>
      <progress max={count} value={decided} aria-label={`Findings decided in ${documentLabel(item)}`} />
      <span className="document-next-step">{decided === count ? 'All choices made' : `${count - decided} ${count - decided === 1 ? 'detail needs' : 'details need'} your choice`}</span>
    </div>
  )
}

export function DocumentTable({
  items,
  workspaceId,
  now,
  onDelete,
  selected,
  pending,
  preferencePending,
  onSelect,
  onSelectVisible,
  onPreference,
  onRenew,
}: {
  items: DocumentIndexView[]
  workspaceId: string
  now: number
  onDelete: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
  selected: Set<string>
  pending: boolean
  preferencePending: Set<string>
  onSelect: (id: string, value: boolean) => void
  onSelectVisible: (value: boolean) => void
  onPreference: (item: DocumentIndexView, value: DocumentPreferenceRequest) => void
  onRenew: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
}) {
  const selectable = items.slice(0, 50)
  const allSelected = selectable.every((item) => selected.has(item.id))
  return (
    <table className="documents-table" aria-label="Documents">
      <caption>
        <div className="document-selection-heading">
          <label className="document-select-visible"><input id="document-select-visible" type="checkbox" checked={allSelected}
            ref={(node) => { if (node) node.indeterminate = !allSelected && selectable.some((item) => selected.has(item.id)) }}
            disabled={pending} onChange={(event) => onSelectVisible(event.target.checked)} /> Select visible</label>
          <span>Select reviews to organize them together. Up to 50 at once.</span>
        </div>
      </caption>
      <colgroup>
        <col className="document-select-col" />
        <col className="document-name-col" />
        <col className="document-progress-col" />
        <col className="document-retention-col" />
        <col className="document-actions-col" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" className="document-select-cell"><span className="sr-only">Selection</span></th>
          <th scope="col">Document</th>
          <th scope="col">Review status</th>
          <th scope="col">Available until</th>
          <th scope="col">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const title = documentLabel(item)
          const lifetime = retention(item, now)
          const unavailable = lifetime.expired || item.status === 'deleted'
          const example = title.startsWith('Example · ')
          const displayTitle = example ? title.slice('Example · '.length) : title
          return (
            <tr key={item.id} className="document-row">
              <td className="document-select-cell"><label className="document-select-target"><input type="checkbox" aria-label={`Select ${title}`}
                checked={selected.has(item.id)} disabled={pending || (!selected.has(item.id) && selected.size >= 50)}
                onChange={(event) => onSelect(item.id, event.target.checked)} /><span className="sr-only">Select {title}</span></label></td>
              <th scope="row" className="document-name-cell">
                <div className="document-identity">
                  <span
                    className={`document-file-icon ${['ready', 'exported'].includes(item.status) ? 'is-reviewed' : ''}`}
                  >
                    <FileText size={19} strokeWidth={1.5} aria-hidden="true" />
                  </span>
                  <div className="document-copy">
                    {unavailable ? (
                      <span className="document-title document-muted">{displayTitle}</span>
                    ) : (
                      <Link className="document-title" to={`/documents/${item.id}/edit`} aria-label={title}>
                        {displayTitle}
                      </Link>
                    )}
                    <div className="document-meta">
                      {item.favorite && <span className="document-flag"><Star size={12} aria-hidden="true" /> Favorite</span>}
                      {item.pinned && <span className="document-flag"><Pin size={12} aria-hidden="true" /> Pinned</span>}
                      {!item.is_owner && <span className="document-example">Assigned to you</span>}
                      {example && <span className="document-example">Example</span>}
                      <time
                        dateTime={item.updated_at}
                        title={`Updated ${new Date(item.updated_at).toLocaleString()}`}
                        aria-label={`Updated ${new Date(item.updated_at).toLocaleString()}`}
                      >
                        Edited {relativeEdit(item.updated_at, now)}
                      </time>
                      <span className="document-created">
                        <span aria-hidden="true">· </span>
                        <time dateTime={item.created_at} title={new Date(item.created_at).toLocaleString()}>
                          Created {shortDate(item.created_at)}
                        </time>
                      </span>
                    </div>
                  </div>
                </div>
              </th>
              <td className="document-progress-cell">
                <StatusBadge status={lifetime.expired ? 'expired' : item.status} />
                <ReviewProgress item={lifetime.expired ? { ...item, status: 'expired' } : item} />
              </td>
              <td className={`document-retention-cell ${lifetime.urgent ? 'is-urgent' : ''}`}>
                <span className="document-retention-label">
                  <Clock3 size={13} aria-hidden="true" /> {lifetime.label}
                </span>
                <time
                  dateTime={item.expires_at}
                  title={new Date(item.expires_at).toLocaleString()}
                  aria-label={`Expires ${new Date(item.expires_at).toLocaleString()}`}
                >
                  {shortDate(item.expires_at)}
                </time>
              </td>
              <td className="document-actions-cell">
                <DocumentActions
                  item={item}
                  workspaceId={workspaceId}
                  unavailable={unavailable}
                  onDelete={onDelete}
                  preferencePending={pending || preferencePending.has(item.id)}
                  onPreference={onPreference}
                  onRenew={onRenew}
                />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
