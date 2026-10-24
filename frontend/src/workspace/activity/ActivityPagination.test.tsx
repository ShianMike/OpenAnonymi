import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import type { AdminActivityView, DocumentIndexView } from '../../api/client'
import { ActivityPagination, ActivityTimeline } from './ActivityTimeline'
import { ACTIVITY_PAGE_SIZE, activityWindow, matchesEvent, eventContext, type ActivityEntry } from './activityPresentation'
import { ActivityEventDetails } from './ActivityEventDialog'
import { ActivityFeed } from './ActivityFeed'

it('pages every event once, clamps after filters shrink the list, and handles empty results', () => {
  const events = Array.from({ length: 27 }, (_, index) => index)
  const visited = Array.from({ length: Math.ceil(events.length / ACTIVITY_PAGE_SIZE) }, (_, page) => {
    const range = activityWindow(events.length, page)
    expect(range.end - range.start).toBeLessThanOrEqual(ACTIVITY_PAGE_SIZE)
    return events.slice(range.start, range.end)
  }).flat()
  expect(visited).toEqual(events)
  expect(activityWindow(1, 4)).toEqual({ page: 0, pages: 1, start: 0, end: 1 })
  expect(activityWindow(0, -1)).toEqual({ page: 0, pages: 1, start: 0, end: 0 })
  const noop = () => {}
  const html = renderToStaticMarkup(<ActivityPagination page={2} total={27} onPrevious={noop} onNext={noop} />)
  expect(html).toContain('Events 25–27 of 27')
  expect(html.match(/<button[^>]*aria-label="Next events"[^>]*>/)?.[0]).toContain('disabled')
  const cursorPage = renderToStaticMarkup(<ActivityPagination page={0} total={6} hasMore onPrevious={noop} onNext={noop} />)
  expect(cursorPage.match(/<button[^>]*aria-label="Next events"[^>]*>/)?.[0]).not.toContain('disabled')
  expect(cursorPage).not.toContain('of 6')
})

it('groups dates once, opens inspect controls, and labels unavailable reviews without guessing their state', () => {
  const events: ActivityEntry[] = [
    { event_code: 'document_deleted', outcome: 'completed', document_id: 'unavailable', occurred_at: '2026-10-08T10:00:00Z' },
    { event_code: 'output_copied', outcome: 'completed', document_id: null, occurred_at: '2026-10-08T09:00:00Z' },
    { event_code: 'workspace_rule_saved', outcome: 'failed', document_id: null, occurred_at: '2026-10-07T09:00:00Z' },
  ]
  const html = renderToStaticMarkup(<MemoryRouter><ActivityTimeline events={events} documents={{}} workspaceId="synthetic" asOf="2026-10-08T11:00:00Z" /></MemoryRouter>)
  expect(html).not.toContain('href=')
  expect(html).toContain('Review record')
  expect(html).toContain('activity-failed')
  expect(html).toContain('aria-label="Inspect Review deleted')
  expect(html.match(/class="activity-day-heading"/g)).toHaveLength(2)
  expect(html).not.toContain('Completed')
  expect(events.filter(event => matchesEvent(event, {}, 'COPIED', 'outputs'))).toEqual([events[1]])
  expect(events.filter(event => matchesEvent(event, {}, '', 'workspace'))).toEqual([events[2]])
  expect(events.filter(event => matchesEvent(event, {}, 'rule', 'workspace', 'failed'))).toEqual([events[2]])
  expect(events.filter(event => matchesEvent(event, {}, '', 'all', 'completed'))).toEqual(events.slice(0, 2))
  expect(eventContext({ ...events[0], event_code: 'second_factor_enabled', document_id: null }, {})).toBe('Account security')
})

it('discloses the personal feed limit and never adds administrator data to member events', () => {
  const event: ActivityEntry = { event_code: 'scan_completed', outcome: 'completed', document_id: 'unavailable', occurred_at: '2026-10-08T10:00:00Z' }
  const member = renderToStaticMarkup(<MemoryRouter><ActivityFeed workspaceId="workspace" documents={{}} value={{ own_events: [event], own_total: 101, workspace_counts: null,
    since: '2026-09-08T11:00:00Z', as_of: '2026-10-08T11:00:00Z' }} /></MemoryRouter>)
  expect(member).toContain('latest 1 of 101 events')
  expect(member).not.toContain('Export CSV')
  const details = renderToStaticMarkup(<MemoryRouter><Dialog.Root><ActivityEventDetails event={event} documents={{}} workspaceId="workspace" /></Dialog.Root></MemoryRouter>)
  expect(details).toContain('A review link isn’t available')
  expect(details).not.toContain('href=')
  expect(details).not.toContain('Performed by')
  expect(details).not.toContain('Decision changes')
})

it('renders only recorded administrator changes and only links to accessible review history', () => {
  const event: AdminActivityView['events'][number] = { id: 'event', actor_id: 'actor', document_id: 'review',
    event_code: 'review_edit_undone', outcome: 'completed', occurred_at: '2026-10-08T10:00:00Z', decision_version: 0,
    decision_change_count: 260, decision_changes: [{ finding_id: 'finding', category: 'email', before_action: 'redact', before_style: 'partial_mask',
      before_option: 'email_domain', after_action: null, after_style: null, after_option: null }] }
  const details = renderToStaticMarkup(<MemoryRouter><Dialog.Root><ActivityEventDetails event={event} documents={{ review: { id: 'review', title: '<Private review>', status: 'draft' } as DocumentIndexView }} workspaceId="workspace" currentUserId="actor" /></Dialog.Root></MemoryRouter>)
  expect(details).toContain('Performed by</dt><dd>You')
  expect(details).toContain('Member ID</dt><dd><code>actor')
  expect(details).toContain('Hide · Show email domain')
  expect(details).toContain('Undecided')
  expect(details).toContain('first 1 of 260 recorded changes')
  expect(details).toContain('Decision version</dt><dd>0')
  expect(details).toContain('&lt;Private review&gt;')
  expect(details).toContain('href="/workspaces/workspace/documents/review/history"')
  const unavailable = renderToStaticMarkup(<MemoryRouter><Dialog.Root><ActivityEventDetails event={{ ...event, actor_id: null, outcome: 'failed' }} documents={{}} workspaceId="workspace" /></Dialog.Root></MemoryRouter>)
  expect(unavailable).toContain('System or removed member')
  expect(unavailable).toContain('is-failed')
  expect(unavailable).not.toContain('href=')
})
