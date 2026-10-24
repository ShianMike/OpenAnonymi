import { Check } from 'lucide-react'
import { dayKey, dayLabel } from '../workspace/activity/activityPresentation'
import { relativeEdit } from '../workspace/documents/documentPresentation'
import type { Notification } from './api'
import { notificationEvents } from './notificationPresentation'

export function NotificationList({ items, pending, onRead, onOpen, now }: {
  items: Notification[]; pending: string | null; onRead: (id: string) => void
  onOpen: (id: string, trigger: HTMLButtonElement) => void; now: number
}) {
  const days = new Map<string, Notification[]>()
  for (const item of items) {
    const key = dayKey(item.created_at)
    if (!days.has(key)) days.set(key, [])
    days.get(key)!.push(item)
  }
  return <>{Array.from(days, ([key, rows]) => {
    const label = dayLabel(rows[0].created_at, new Date(now).toISOString())
    return <section className="notification-day" key={key} aria-label={`${label} notifications`}>
      <h2>{label}</h2>
      <ul className="notification-list">{rows.map(item => {
        const available = item.document_available && !!item.document_id
        const title = available ? item.title || 'Untitled review' : 'Review unavailable'
        const message = notificationEvents[item.event_code].message
        return <li key={item.id} className="notification-row" data-unread={!item.read_at || undefined}>
          <span className="notification-dot" aria-hidden="true" />
          <span className="sr-only">{item.read_at ? 'Read' : 'Unread'}</span>
          <button type="button" className="notification-content" data-unavailable={!available || undefined} aria-haspopup="dialog" disabled={!!pending}
            onClick={event => onOpen(item.id, event.currentTarget)}>
            <strong>{title}</strong><span>{message}</span>{!available && <small>Expired, removed, or no longer accessible.</small>}
          </button>
          <div className="notification-row-tools">
            <time dateTime={item.created_at} title={new Date(item.created_at).toLocaleString()}>{relativeEdit(item.created_at, now)}</time>
            {!item.read_at && <button type="button" className="notification-read" disabled={!!pending} title="Mark as read"
              aria-label={`Mark as read: ${title}, ${message}`} onClick={() => onRead(item.id)}><Check size={16} aria-hidden="true" /></button>}
          </div>
        </li>
      })}</ul>
    </section>
  })}</>
}
