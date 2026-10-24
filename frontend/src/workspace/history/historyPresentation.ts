import type { DocumentHistoryView } from '../../api/client'
import { dayKey, dayLabel } from '../activity/activityPresentation'

export function historyAvailable(history: DocumentHistoryView, now: number) {
  return !['expired', 'deleted'].includes(history.status) && Date.parse(history.expires_at) > now
}

export function historyDays(events: DocumentHistoryView['events'], asOf: string) {
  const days = new Map<string, { key: string; label: string; events: DocumentHistoryView['events'] }>()
  for (const event of events) {
    const key = dayKey(event.occurred_at)
    if (!days.has(key)) days.set(key, { key, label: dayLabel(event.occurred_at, asOf), events: [] })
    days.get(key)!.events.push(event)
  }
  return [...days.values()]
}
