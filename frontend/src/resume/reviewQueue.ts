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
  if (item.status === 'draft') return item.is_owner ? 'Start with suggestions or mark details yourself.' : 'Mark details while the owner prepares suggestions.'
  if (item.status === 'scanning') return 'Suggestions are being checked. Open to see the latest progress.'
  if (item.status === 'failed') return item.is_owner ? 'Retry suggestions, then review the findings.' : 'The owner can retry suggestions. You can still review the text.'
  if (['ready', 'exported'].includes(item.status)) return item.is_owner ? 'Revisit your confirmed output and sharing options.' : 'Owner confirmed · check the output and your approval.'
  const remaining = Math.max(0, item.finding_count - item.decided_count)
  if (remaining) return `${remaining} ${remaining === 1 ? 'finding needs' : 'findings need'} a decision.`
  return item.is_owner ? 'Read the full output, then confirm this version.' : 'Decisions saved · the owner confirms before you approve.'
}
