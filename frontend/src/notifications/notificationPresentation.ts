import type { Notification, NotificationDetail } from './api'

export const notificationEvents: Record<Notification['event_code'], { title: string; message: string }> = {
  review_assigned: { title: 'Review assigned', message: 'You were assigned to this review.' },
  review_unassigned: { title: 'Assignment removed', message: 'Your reviewer assignment was removed.' },
  approval_requested: { title: 'Approval requested', message: 'You were asked to approve a saved version of this review.' },
  review_approved: { title: 'Review approved', message: 'The assigned reviewer approved a saved version of your review.' },
  approval_invalidated: { title: 'Review changed', message: 'A change to the review invalidated an earlier approval or approval request.' },
  comment_added: { title: 'Comment added', message: 'A comment was added to this review.' },
}

export function currentReview(detail: NotificationDetail) {
  const current = detail.current
  if (!current) return { title: 'Review unavailable', message: 'This review expired, was removed, or is no longer shared with you.' }
  if (current.approved_at) return { title: 'Current version approved', message: 'The assigned reviewer has approved the current saved version.' }
  if (current.require_approval && !current.reviewer_active) return { title: 'A reviewer is needed', message: 'The owner needs to assign an active reviewer before this version can receive approval.' }
  if (current.require_approval && current.confirmed_at) return { title: 'Awaiting reviewer approval', message: current.is_owner ? 'The owner has confirmed this version. The assigned reviewer has yet to approve it.' : 'The owner has confirmed this version. Read the full output before you approve it.' }
  if (current.confirmed_at) return { title: 'Current version confirmed', message: 'The owner has confirmed this version. Reviewer approval is not required.' }
  const states = {
    draft: ['Draft', 'Suggestions have not been confirmed for this version.'],
    scanning: ['Checking the document', 'Suggestions are being generated.'],
    needs_review: ['Review in progress', 'The current version still needs the owner’s final confirmation.'],
    failed: ['Suggestions need another try', 'Open the review to check the scan and try again.'],
    ready: ['Confirmation needs checking', 'Open the review to check the current confirmation.'],
    exported: ['Confirmation needs checking', 'Open the review to check the current confirmation.'],
    expired: ['Review unavailable', 'The document’s retention period has ended.'],
    deleted: ['Review unavailable', 'This document was removed.'],
  } as const
  const [title, message] = states[current.status]
  return { title, message }
}

export function notificationDestination(detail: NotificationDetail) {
  const { notification, current } = detail
  if (!notification.document_available || !notification.document_id || !current) return null
  const base = `/documents/${encodeURIComponent(notification.document_id)}/edit`
  // shortcut: stored events have no comment ID; add one before linking to individual comments.
  if (notification.event_code === 'comment_added') return { to: `${base}?panel=discussion`, label: 'Open discussion' }
  if (notification.event_code === 'review_approved') return { to: `${base}?view=output`, label: 'View reviewed output' }
  if (['approval_requested', 'approval_invalidated', 'review_assigned'].includes(notification.event_code) && !current.is_owner) {
    return { to: `${base}?panel=reviewer`, label: current.confirmed_at && !current.approved_at && current.require_approval ? 'Review for approval' : 'Open your review' }
  }
  return { to: base, label: 'Open review' }
}
