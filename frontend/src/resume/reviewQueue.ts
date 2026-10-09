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
  if (item.status === 'draft') return item.is_owner ? 'Find private details, then choose what to share.' : 'Check the text while the owner prepares suggestions.'
  if (item.status === 'scanning') return 'Checking for private details. Open for the latest progress.'
  if (item.status === 'failed') return item.is_owner ? 'Run the check again, then review each detail.' : 'The owner can run the check again. You can still review the text.'
  if (['ready', 'exported'].includes(item.status)) return item.is_owner ? 'Open the reviewed text and sharing options.' : 'The owner has confirmed. Read the text before approving.'
  const remaining = Math.max(0, item.finding_count - item.decided_count)
  if (remaining) return `${remaining} ${remaining === 1 ? 'detail needs' : 'details need'} your choice.`
  return item.is_owner ? 'Read the reviewed text, then confirm.' : 'The owner needs to confirm before you can approve.'
}
