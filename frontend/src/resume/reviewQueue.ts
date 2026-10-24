import type { DocumentIndexView } from '../api/client'

export function availableReview(item: DocumentIndexView, now: number): boolean {
  return Boolean(item.current_revision_id) && !['expired', 'deleted'].includes(item.status) &&
    Date.parse(item.expires_at) > now
}

export function reviewQueue(items: DocumentIndexView[], lastId: string | null, now: number) {
  const available = items.filter((item) => availableReview(item, now))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at) || a.id.localeCompare(b.id))
  return {
    last: available.find((item) => item.id === lastId) ?? null,
    assigned: available.filter((item) => !item.is_owner),
    unfinished: available.filter((item) => item.is_owner && !['ready', 'exported'].includes(item.status)),
  }
}

export function reviewNextStep(item: DocumentIndexView): string {
  if (item.status === 'draft') return item.is_owner ? 'Find private details to review.' : 'Waiting for the owner’s scan.'
  if (item.status === 'scanning') return 'The scan is running.'
  if (item.status === 'failed') return item.is_owner ? 'Run the scan again.' : 'The owner needs to retry the scan.'
  if (['ready', 'exported'].includes(item.status)) return item.is_owner ? 'Ready to share.' : 'Read and approve the output.'
  const remaining = Math.max(0, item.finding_count - item.decided_count)
  if (remaining) return `${remaining} ${remaining === 1 ? 'detail needs' : 'details need'} your choice.`
  return item.is_owner ? 'Read and confirm the output.' : 'Waiting for the owner’s confirmation.'
}
