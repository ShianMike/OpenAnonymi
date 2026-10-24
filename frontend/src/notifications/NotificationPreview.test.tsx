import * as Dialog from '@radix-ui/react-dialog'
import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { NotificationDetail } from './api'
import { currentReview, notificationDestination } from './notificationPresentation'
import { NotificationDetailContent } from './NotificationPreview'

const detail: NotificationDetail = {
  notification: { id: 'event', document_id: 'document', workspace_id: 'workspace', actor_id: null,
    title: 'Fictional review', event_code: 'approval_requested', created_at: '2026-10-23T10:00:00Z', read_at: null, document_available: true },
  current: { status: 'ready', is_owner: false, reviewer_active: true, require_approval: true,
    confirmed_at: '2026-10-23T10:00:00Z', approved_at: null },
}
function render(value: NotificationDetail) {
  return renderToStaticMarkup(<MemoryRouter><Dialog.Root><NotificationDetailContent detail={value} read pending={false} onNavigate={() => {}} /></Dialog.Root></MemoryRouter>)
}

it('shows an old request alongside the actual current approval rather than asking for approval again', () => {
  const approved = { ...detail, current: { ...detail.current!, approved_at: '2026-10-23T10:30:00Z' } }
  const html = render(approved)
  expect(html).toContain('You were asked to approve a saved version')
  expect(html).toContain('Current version approved')
  expect(html).not.toContain('Review for approval')
  expect(notificationDestination(approved)?.label).toBe('Open your review')
  expect(currentReview(detail).title).toBe('Awaiting reviewer approval')
  expect(notificationDestination(detail)).toEqual({ to: '/documents/document/edit?panel=reviewer', label: 'Review for approval' })
})

it('does not claim an earlier approval still applies after source or decisions change', () => {
  const changed = { ...detail, notification: { ...detail.notification, event_code: 'review_approved' as const },
    current: { ...detail.current!, status: 'needs_review' as const, confirmed_at: null, approved_at: null } }
  expect(currentReview(changed).title).toBe('Review in progress')
  expect(render(changed)).not.toContain('Current version approved')
  expect(notificationDestination(changed)?.to).toBe('/documents/document/edit?view=output')
})

it('never exposes a cached title or a destination when access is unavailable', () => {
  const unavailable = { ...detail, notification: { ...detail.notification, document_available: false, title: 'Hidden private title' }, current: null }
  const html = render(unavailable)
  expect(html).not.toContain('Hidden private title')
  expect(html).toContain('Review unavailable')
  expect(html).not.toContain('/documents/document')
  expect(notificationDestination(unavailable)).toBeNull()
})

it('opens the discussion without pretending an old notification identifies a current comment', () => {
  const comment = { ...detail, notification: { ...detail.notification, event_code: 'comment_added' as const } }
  expect(notificationDestination(comment)).toEqual({ to: '/documents/document/edit?panel=discussion', label: 'Open discussion' })
  expect(render(comment)).toContain('Earlier comments may no longer be available.')
})

it('distinguishes an unassigned reviewer from an approval that is currently pending', () => {
  expect(currentReview({ ...detail, current: { ...detail.current!, reviewer_active: false } }).title).toBe('A reviewer is needed')
  expect(currentReview({ ...detail, current: { ...detail.current!, require_approval: false } }).title).toBe('Current version confirmed')
  expect(notificationDestination({ ...detail, current: { ...detail.current!, is_owner: true } })?.label).toBe('Open review')
})
