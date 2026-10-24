import type { DocumentIndexView } from '../../api/client'
import { availableReview } from '../../resume/reviewQueue'

export const documentViews = [
  { value: 'all', label: 'All documents' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'shared', label: 'Shared with you' },
  { value: 'completed', label: 'Completed' },
  { value: 'favorites', label: 'Favorites' },
] as const
export type DocumentView = typeof documentViews[number]['value']
export type DocumentSort = 'updated' | 'newest' | 'oldest' | 'expiring' | 'title'
export const documentStatuses = [
  { value: 'all', label: 'Any status' }, { value: 'draft', label: 'Draft' },
  { value: 'scanning', label: 'Scanning' }, { value: 'needs_review', label: 'Needs review' },
  { value: 'ready', label: 'Ready to share' }, { value: 'exported', label: 'Exported' },
  { value: 'failed', label: 'Scan failed' }, { value: 'expired', label: 'Expired' },
] as const

export function readDocumentQuery(params: URLSearchParams) {
  const view = documentViews.find(item => item.value === params.get('view'))?.value ?? 'all'
  const status = documentStatuses.find(item => item.value === params.get('status'))?.value ?? 'all'
  const sort = (['updated', 'newest', 'oldest', 'expiring', 'title'] as const)
    .find(value => value === params.get('sort')) ?? 'updated'
  const page = Number(params.get('page') ?? 0)
  return { view, status, sort, search: (params.get('q') ?? '').slice(0, 200),
    page: Number.isSafeInteger(page) && page >= 0 ? page : 0 }
}

export function currentDocuments(items: DocumentIndexView[], now: number): DocumentIndexView[] {
  return items.filter(item => item.status !== 'deleted').map(item => availableReview(item, now)
    ? item : { ...item, title: null, status: 'expired', favorite: false, pinned: false })
}

export function matchesDocumentView(item: DocumentIndexView, view: DocumentView) {
  if (view === 'all') return true
  if (item.status === 'expired' || item.status === 'deleted') return false
  if (view === 'shared') return !item.is_owner
  if (view === 'in_progress') return item.is_owner && !['ready', 'exported'].includes(item.status)
  if (view === 'completed') return ['ready', 'exported'].includes(item.status)
  return item.favorite
}

export function visibleDocuments(items: DocumentIndexView[], query: ReturnType<typeof readDocumentQuery>) {
  const search = query.search.trim().toLocaleLowerCase()
  return items.filter(item => matchesDocumentView(item, query.view) &&
    matchesStatus(item, query.status) && (!search || documentLabel(item).toLocaleLowerCase().includes(search)))
    .sort((left, right) => {
      if (left.pinned !== right.pinned) return left.pinned ? -1 : 1
      if (query.sort === 'title') return documentLabel(left).localeCompare(documentLabel(right)) || left.id.localeCompare(right.id)
      if (query.sort === 'expiring') return left.expires_at.localeCompare(right.expires_at) || left.id.localeCompare(right.id)
      if (query.sort === 'oldest') return left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id)
      const field = query.sort === 'newest' ? 'created_at' : 'updated_at'
      return right[field].localeCompare(left[field]) || left.id.localeCompare(right.id)
    })
}

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
