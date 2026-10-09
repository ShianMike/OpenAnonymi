import { Link } from 'react-router-dom'
import { ArrowUpRight, Check, History } from 'lucide-react'
import { eventName } from '../events'
import { ListPagination } from '../../ui/ListPagination'
import {
  ACTIVITY_PAGE_SIZE,
  dayLabel,
  eventGroup,
  eventIcon,
  reviewLabel,
  type ActivityEntry,
  type DocumentMap,
} from './activityPresentation'

export function ActivityTimeline({ events, documents, workspaceId, asOf }: {
  events: ActivityEntry[]
  documents: DocumentMap
  workspaceId: string
  asOf: string
}) {
  return <ol className="activity-timeline" aria-label="Your recent activity">
    {events.map((event, index) => {
      const Icon = eventIcon(event.event_code)
      const document = event.document_id ? documents[event.document_id] : undefined
      const success = ['success', 'completed'].includes(event.outcome)
      const content = <><strong>{eventName(event.event_code)}</strong>
        <span>{document ? reviewLabel(document) : event.document_id ? 'Review history' : 'Workspace activity'}
          {document && <ArrowUpRight size={12} aria-hidden="true" />}</span></>
      return <li className="activity-event" key={`${event.occurred_at}-${index}`}>
        <span className={`activity-event-icon is-${eventGroup(event.event_code)}`}><Icon size={17} strokeWidth={1.6} aria-hidden="true" /></span>
        {document ? <Link className="activity-event-detail" to={`/workspaces/${workspaceId}/documents/${document.id}/history`}>{content}</Link>
          : <div className="activity-event-detail">{content}</div>}
        <div className="activity-event-meta">
          <time dateTime={event.occurred_at} title={new Date(event.occurred_at).toLocaleString()}>
            <span>{dayLabel(event.occurred_at, asOf)}</span>
            <span>{new Date(event.occurred_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</span>
          </time>
          <span className={`activity-outcome${success ? '' : ' is-failed'}`}>
            {success && <Check size={12} aria-hidden="true" />}{success ? 'Completed' : event.outcome.replaceAll('_', ' ')}
          </span>
        </div>
      </li>
    })}
  </ol>
}

export function ActivityPagination({ page, total, hasMore = false, pending = false, onPrevious, onNext }: {
  page: number; total: number; hasMore?: boolean; pending?: boolean
  onPrevious: () => void; onNext: () => void
}) {
  return <ListPagination page={page} total={total} pageSize={ACTIVITY_PAGE_SIZE} label="Events"
    hasMore={hasMore} pending={pending} onPrevious={onPrevious} onNext={onNext} />
}

export function ActivityEmpty({ filtered, onClear, workspaceId }: { filtered: boolean; onClear: () => void; workspaceId: string }) {
  return <div className="activity-empty">
    <History size={28} strokeWidth={1.4} aria-hidden="true" />
    <h3>{filtered ? 'No matching activity' : 'No activity yet'}</h3>
    <p>{filtered ? 'Try a different filter.' : 'Review actions will appear here as you work.'}</p>
    {filtered && <button className="quiet-button" type="button" onClick={onClear}>Clear filters</button>}
    {!filtered && <Link className="button-secondary" to={`/new?workspace=${workspaceId}`}>Create a review</Link>}
  </div>
}
