import type { ActivityView, AdminActivityView, DocumentIndexView } from '../../api/client'
import { eventName } from '../events'
import { pageWindow } from '../../ui/pagination'

export type ActivityEntry = ActivityView['own_events'][number]
export type ActivityEvent = ActivityEntry | AdminActivityView['events'][number]
export type ActivityFilter = 'all' | 'reviews' | 'outputs' | 'workspace'
export type ActivityOutcome = 'all' | 'completed' | 'failed'
export type DocumentMap = Record<string, DocumentIndexView>

export const ACTIVITY_PAGE_SIZE = 12
export function activityWindow(total: number, requestedPage: number) {
  return pageWindow(total, requestedPage, ACTIVITY_PAGE_SIZE)
}

export function eventGroup(code: string): Exclude<ActivityFilter, 'all'> {
  if (code.startsWith('output_')) return 'outputs'
  if (/^(workspace_|member_|preset_|second_factor_|backup_codes_|device_|other_devices_)/.test(code)) return 'workspace'
  return 'reviews'
}

export function eventContext(event: ActivityEntry, documents: DocumentMap): string {
  const document = event.document_id ? documents[event.document_id] : undefined
  if (document) return reviewLabel(document)
  if (event.document_id) return 'Review record'
  if (/^(second_factor_|backup_codes_|device_|other_devices_)/.test(event.event_code)) return 'Account security'
  return eventGroup(event.event_code) === 'workspace' ? 'Workspace settings' : 'Review activity'
}

export function reviewLabel(document: DocumentIndexView): string {
  return (
    document.title?.replace(/^Example\s*·\s*/, '') ||
    (document.status === 'expired' ? 'Expired review' : 'Untitled review')
  )
}

export function matchesEvent(
  event: ActivityEntry,
  documents: DocumentMap,
  search: string,
  filter: ActivityFilter,
  outcome: ActivityOutcome = 'all',
) {
  const document = event.document_id ? documents[event.document_id] : undefined
  return (
    (filter === 'all' || eventGroup(event.event_code) === filter) &&
    (outcome === 'all' || event.outcome === outcome) &&
    `${eventName(event.event_code)} ${document ? reviewLabel(document) : ''} ${event.outcome} ${eventContext(event, documents)}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase())
  )
}

export function dayKey(value: string): string {
  return new Date(value).toLocaleDateString('en-CA')
}

export function dayLabel(value: string, asOf: string): string {
  if (dayKey(value) === dayKey(asOf)) return 'Today'
  const yesterday = new Date(asOf)
  yesterday.setDate(yesterday.getDate() - 1)
  if (dayKey(value) === dayKey(yesterday.toISOString())) return 'Yesterday'
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(new Date(value).getFullYear() !== new Date(asOf).getFullYear() ? { year: 'numeric' as const } : {}),
  })
}

export function periodLabel(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
