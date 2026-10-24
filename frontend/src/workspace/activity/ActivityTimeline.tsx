import { Link } from 'react-router-dom'
import { ChevronRight, History } from 'lucide-react'
import { eventName } from '../events'
import { ListPagination } from '../../ui/ListPagination'
import { ActivityEventDialog } from './ActivityEventDialog'
import { ACTIVITY_PAGE_SIZE, dayKey, dayLabel, eventContext, periodLabel, type ActivityEvent, type DocumentMap } from './activityPresentation'

export function ActivityTimeline({ events, documents, workspaceId, asOf, currentUserId, label = 'Your recent activity' }: {
  events: ActivityEvent[]; documents: DocumentMap; workspaceId: string; asOf: string; currentUserId?: string; label?: string
}) {
  return <ol className="activity-timeline" aria-label={label}>
    {events.map((event, index) => <li className="activity-event" key={'id' in event ? event.id : `${event.occurred_at}-${index}`}>
      {(index === 0 || dayKey(event.occurred_at) !== dayKey(events[index - 1].occurred_at)) && <div className="activity-day-heading">
        <h2>{dayLabel(event.occurred_at, asOf)}</h2><span>{periodLabel(event.occurred_at)}</span>
      </div>}
      <ActivityEventDialog event={event} documents={documents} workspaceId={workspaceId} currentUserId={currentUserId}
        trigger={<button type="button" className="activity-event-trigger" aria-label={`Inspect ${eventName(event.event_code)} · ${eventContext(event, documents)} · ${new Date(event.occurred_at).toLocaleString()}${event.outcome === 'failed' ? ' · Failed' : ''}`}>
          <time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</time>
          <span className="activity-event-copy"><strong>{eventName(event.event_code)}{event.outcome === 'failed' && <span className="activity-failed">Failed</span>}</strong>
            <span>{eventContext(event, documents)}{'id' in event && <>{' · '}{event.actor_id === currentUserId ? 'You' : event.actor_id ? `Member ${event.actor_id.slice(0, 8)}` : 'System or removed member'}{event.decision_change_count > 0 && ` · ${event.decision_change_count} decision change${event.decision_change_count === 1 ? '' : 's'}`}</>}</span>
          </span><ChevronRight size={15} aria-hidden="true" />
        </button>} />
    </li>)}
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
    <History size={25} strokeWidth={1.4} aria-hidden="true" />
    <h3>{filtered ? 'No events match' : 'Nothing recorded in this period'}</h3>
    <p>{filtered ? 'Try a different search or clear the filters.' : 'New review and workspace actions will appear here.'}</p>
    {filtered ? <button className="activity-button" type="button" onClick={onClear}>Clear filters</button>
      : <Link className="activity-button" to={`/new?workspace=${workspaceId}`}>Start a review</Link>}
  </div>
}
