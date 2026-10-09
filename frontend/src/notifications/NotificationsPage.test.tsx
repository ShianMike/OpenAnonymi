import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { NotificationList } from './NotificationsPage'
import type { Notification } from './api'

it('hides unavailable review details while retaining its unread action and exact timestamp', () => {
  const now = Date.parse('2026-10-08T12:00:00Z')
  const notification: Notification = { id: 'available', workspace_id: 'workspace', actor_id: null,
    document_id: 'review', event_code: 'approval_requested', title: 'Fictional review',
    created_at: '2026-10-08T11:30:00Z', read_at: null, document_available: true }
  const unavailable = { ...notification, id: 'unavailable', document_id: 'revoked-review',
    title: 'Private title must stay hidden', document_available: false }
  const read = { ...notification, id: 'read', read_at: '2026-10-08T11:40:00Z' }
  const html = renderToStaticMarkup(<MemoryRouter><NotificationList items={[notification, unavailable, read]}
    pending={null} onRead={() => {}} now={now} /></MemoryRouter>)
  expect(html).toContain('href="/documents/review/edit"')
  expect(html).not.toContain('Private title must stay hidden')
  expect(html).not.toContain('/documents/revoked-review/edit')
  expect(html).toContain('Document unavailable.')
  expect(html).toContain('dateTime="2026-10-08T11:30:00Z"')
  expect(html.match(/Mark as read: Your approval was requested/g)).toHaveLength(2)
  expect(html).toContain('aria-disabled="true" tabindex="-1"')
})
