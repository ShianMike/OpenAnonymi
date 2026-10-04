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
  if (item.status === 'draft') return <span className="document-progress-placeholder">Not scanned yet</span>
  if (item.status === 'scanning') return <span className="document-progress-placeholder">Scanning…</span>
  if (item.status === 'failed')
    return <span className="document-progress-placeholder">Scan needs a retry</span>
  if (count === 0)
    return (
      <span className="document-progress-empty">
        <Check size={14} aria-hidden="true" /> No findings
      </span>
    )
  return (
    <div className={`document-progress ${decided === count ? 'is-decided' : ''}`}>
      <span className="document-progress-label">
        <strong>
          {decided}
          <span> / {count}</span>
        </strong>
        <span>decided</span>
      </span>
      <progress max={count} value={decided} aria-label={`Findings decided in ${documentLabel(item)}`} />
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
  onPreference: (item: DocumentIndexView, value: DocumentPreferenceRequest) => void
  onRenew: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
}) {
  return (
    <table className="documents-table" aria-label="Documents">
      <colgroup>
        <col className="document-select-col" />
        <col className="document-name-col" />
        <col className="document-status-col" />
        <col className="document-progress-col" />
        <col className="document-retention-col" />
        <col className="document-actions-col" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" className="document-select-cell"><span className="sr-only">Selection</span></th>
          <th scope="col">Document</th>
          <th scope="col">Status</th>
          <th scope="col">Review progress</th>
          <th scope="col">Retention</th>
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
              <td className="document-select-cell"><input type="checkbox" aria-label={`Select ${title}`}
                checked={selected.has(item.id)} disabled={pending || (!selected.has(item.id) && selected.size >= 50)}
                onChange={(event) => onSelect(item.id, event.target.checked)} /></td>
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
              <td className="document-status-cell">
                <StatusBadge status={lifetime.expired ? 'expired' : item.status} />
              </td>
              <td className="document-progress-cell">
                <span className="document-mobile-label">Review progress</span>
                <ReviewProgress item={item} />
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
