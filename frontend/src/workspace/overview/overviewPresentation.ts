import type { DocumentIndexView, OverviewView } from '../../api/client'
import { retention } from '../documents/documentPresentation'

export function reviewsInProgress(counts: OverviewView['own_by_status']) {
  return ['draft', 'scanning', 'needs_review', 'failed'].reduce((total, status) => total + (counts[status] ?? 0), 0)
}

export function recentAvailableReviews(items: DocumentIndexView[], now: number) {
  return items.filter(item => item.status !== 'deleted' && !retention(item, now).expired)
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)).slice(0, 5)
}
