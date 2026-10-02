import { Link } from 'react-router-dom'
import { ArrowUpRight, History } from 'lucide-react'
import { eventName } from '../events'
import {
  dayKey,
  dayLabel,
  eventGroup,
  eventIcon,
  reviewLabel,
  type ActivityEntry,
  type DocumentMap,
} from './activityPresentation'

export function ActivityTimeline({
  events,
  documents,
  workspaceId,
  asOf,
}: {
  events: ActivityEntry[]
  documents: DocumentMap
  workspaceId: string
  asOf: string
}) {
  const groups = new Map<string, ActivityEntry[]>()
  for (const event of events) {
    const day = dayKey(event.occurred_at)
    const group = groups.get(day)
    if (group) group.push(event)
    else groups.set(day, [event])
  }
  return (
    <div className="activity-timeline" aria-label="Your recent activity">
      {Array.from(groups, ([day, entries]) => (
        <section className="activity-day" key={day}>
          <h3>
            {dayLabel(entries[0].occurred_at, asOf)}
            <span>
              {entries.length} {entries.length === 1 ? 'event' : 'events'}
            </span>
          </h3>
          <ol>
            {entries.map((event, index) => {
              const Icon = eventIcon(event.event_code)
              const document = event.document_id ? documents[event.document_id] : undefined
              const success = ['success', 'completed'].includes(event.outcome)
              return (
                <li className="activity-event" key={`${event.occurred_at}-${index}`}>
                  <span className={`activity-event-icon is-${eventGroup(event.event_code)}`}>
                    <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
                  </span>
                  <div className="activity-event-detail">
                    <strong>{eventName(event.event_code)}</strong>
                    {document ? (
                      <Link to={`/workspaces/${workspaceId}/documents/${document.id}/history`}>
                        {reviewLabel(document)}
                        <ArrowUpRight size={12} aria-hidden="true" />
                      </Link>
                    ) : (
                      <span className="activity-event-context">
                        {event.document_id ? 'Review history' : 'Workspace activity'}
                      </span>
                    )}
                  </div>
                  <div className="activity-event-meta">
                    <time dateTime={event.occurred_at} title={new Date(event.occurred_at).toLocaleString()}>
                      {new Date(event.occurred_at).toLocaleTimeString(undefined, {
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </time>
                    <span className={`activity-outcome${success ? ' is-success' : ''}`}>
                      <i aria-hidden="true" />
                      {success ? 'Completed' : event.outcome.replaceAll('_', ' ')}
                    </span>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      ))}
    </div>
  )
}

export function ActivityEmpty({ filtered, onClear }: { filtered: boolean; onClear: () => void }) {
  return (
    <div className="activity-empty">
      <History size={32} strokeWidth={1.2} aria-hidden="true" />
      <h3>{filtered ? 'No matching activity' : 'Your story starts here'}</h3>
      <p>
        {filtered ? 'Try another search or event type.' : 'Your review actions will appear here as you work.'}
      </p>
      {filtered && (
        <button className="quiet-button" type="button" onClick={onClear}>
          Clear filters
        </button>
      )}
    </div>
  )
}
