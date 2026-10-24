import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { NotificationsPage } from './NotificationsPage'
import type { useNotifications } from './useNotifications'
import type { Notification } from './api'

const inbox = vi.hoisted(() => ({ data: {} as ReturnType<typeof useNotifications>['data'] }))
vi.mock('./useNotifications', () => ({ useNotifications: () => ({ data: inbox.data, pending: null, notice: '', actionError: '', read: () => {}, loadOlder: () => {}, refresh: () => {} }) }))
const session = { user_id: 'synthetic', csrf_token: 'synthetic' } as SessionView
const item: Notification = { id: 'one', workspace_id: 'workspace', document_id: 'document', actor_id: null,
  event_code: 'review_assigned', title: 'Fictional local review', read_at: null,
  document_available: true, created_at: '2026-10-23T12:00:00Z' }
function ready(items: Notification[], unread = 0, next_cursor: string | null = null) {
  inbox.data = { kind: 'ready', page: { items, next_cursor }, unread, checkedAt: Date.parse('2026-10-23T13:00:00Z') }
}
function render(query = '') {
  return renderToStaticMarkup(<MemoryRouter initialEntries={['/notifications' + query]}><NotificationsPage session={session} /></MemoryRouter>)
}

it('gives an empty inbox a useful action without disabled pagination or zero totals', () => {
  ready([])
  const html = render()
  expect(html).toContain('A quiet inbox')
  expect(html).toContain('Browse documents')
  expect(html).toContain('Preferences')
  expect(html).not.toContain('Page 1 of 1')
  expect(html).not.toContain('0 updates')
  expect(html).not.toContain('Load older updates')
})

it('uses the total unread count even when older unread items have not been loaded', () => {
  ready([{ ...item, read_at: item.created_at }], 7, 'older')
  const html = render('?view=unread')
  expect(html).toContain('Unread<span>7</span>')
  expect(html).toContain('Your unread updates are further back')
  expect(html).toContain('Load older updates')
  expect(html).not.toContain('Fictional local review')
  const markAll = html.match(/<button[^>]*class="notification-mark-all"[^>]*>/)?.[0]
  expect(markAll).toBeDefined()
  expect(markAll).not.toContain('disabled')
})

it('keeps read updates out of the unread view and omits unnecessary older controls when caught up', () => {
  ready([{ ...item, read_at: item.created_at }], 0, 'older')
  const html = render('?view=unread')
  expect(html).toContain('You’re all caught up')
  expect(html).not.toContain('Fictional local review')
  expect(html).not.toContain('Load older updates')
})

it('starts with a bounded feed and reveals older updates on demand', () => {
  ready(Array.from({ length: 25 }, (_, index) => ({ ...item, id: String(index), title: `Local review ${index}` })), 25)
  const html = render()
  expect(html.match(/class="notification-row"/g)).toHaveLength(20)
  expect(html).toContain('Load older updates')
  expect(html).not.toContain('Local review 24')
  expect(html).not.toContain('<table')
})

it('clears document titles from the page when access rechecking fails', () => {
  inbox.data = { kind: 'error', message: 'Your access changed.' }
  const html = render()
  expect(html).toContain('Inbox couldn’t be loaded')
  expect(html).toContain('Try again')
  expect(html).not.toContain('Fictional local review')
  inbox.data = { kind: 'loading' }
  expect(render()).toContain('Checking your inbox…')
})
