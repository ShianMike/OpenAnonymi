import type { DocumentIndexView } from '../../api/client'

export type DocumentSort = 'newest' | 'oldest' | 'expiring' | 'title'

export function documentLabel(item: DocumentIndexView): string {
  return item.title || (item.status === 'expired' ? 'Expired review' : 'Untitled review')
}

export function shortDate(value: string): string {
  const date = new Date(value)
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(date.getFullYear() !== new Date().getFullYear() ? { year: 'numeric' as const } : {}),
  })
}

export function relativeEdit(value: string, now: number): string {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60_000))
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  if (minutes < 10080) return `${Math.floor(minutes / 1440)}d ago`
  return shortDate(value)
}

export function retention(item: DocumentIndexView, now: number) {
  const left = Date.parse(item.expires_at) - now
  const expired = item.status === 'expired' || left <= 0
  return {
    expired,
    urgent: !expired && left <= 86_400_000,
    label: expired
      ? 'Expired'
      : left < 3_600_000
        ? 'Under an hour'
        : left < 86_400_000
          ? `${Math.ceil(left / 3_600_000)}h left`
          : `${Math.ceil(left / 86_400_000)} days left`,
  }
}

export function matchesStatus(item: DocumentIndexView, status: string): boolean {
  return (
    status === 'all' ||
    (status === 'favorites' && item.favorite) ||
    (status === 'complete' ? ['ready', 'exported'].includes(item.status) : item.status === status)
  )
}
