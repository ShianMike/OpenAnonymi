import {
  CheckCheck,
  Download,
  FilePlus2,
  ScanLine,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from 'lucide-react'
import type { ActivityView, DocumentIndexView } from '../../api/client'
import { eventName } from '../events'

export type ActivityEntry = ActivityView['own_events'][number]
export type ActivityFilter = 'all' | 'reviews' | 'outputs' | 'workspace'
export type DocumentMap = Record<string, DocumentIndexView>

export function eventGroup(code: string): Exclude<ActivityFilter, 'all'> {
  if (code.startsWith('output_')) return 'outputs'
  if (/^(workspace_|member_|preset_)/.test(code)) return 'workspace'
  return 'reviews'
}

export function eventIcon(code: string): LucideIcon {
  if (code.startsWith('output_')) return Download
  if (code.startsWith('member_')) return Users
  if (/^(workspace_|preset_)/.test(code)) return SlidersHorizontal
  if (code.startsWith('scan_')) return ScanLine
  if (code === 'document_created') return FilePlus2
  return CheckCheck
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
) {
  const document = event.document_id ? documents[event.document_id] : undefined
  return (
    (filter === 'all' || eventGroup(event.event_code) === filter) &&
    `${eventName(event.event_code)} ${document ? reviewLabel(document) : ''} ${event.outcome}`
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
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    ...(new Date(value).getFullYear() !== new Date(asOf).getFullYear() ? { year: 'numeric' as const } : {}),
  })
}

export function periodLabel(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
