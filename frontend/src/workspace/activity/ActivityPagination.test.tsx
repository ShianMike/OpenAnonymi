import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { ActivityPagination, ActivityTimeline } from './ActivityTimeline'
import { ACTIVITY_PAGE_SIZE, activityWindow, matchesEvent, type ActivityEntry } from './activityPresentation'
import { ActivitySummary } from './ActivitySummary'

it('pages every event once, clamps after filters shrink the list, and handles empty results', () => {
  const events = Array.from({ length: 27 }, (_, index) => index)
  const visited = Array.from({ length: 5 }, (_, page) => {
    const range = activityWindow(events.length, page)
    expect(range.end - range.start).toBeLessThanOrEqual(ACTIVITY_PAGE_SIZE)
    return events.slice(range.start, range.end)
  }).flat()
  expect(visited).toEqual(events)
  expect(activityWindow(1, 4)).toEqual({ page: 0, pages: 1, start: 0, end: 1 })
  expect(activityWindow(0, -1)).toEqual({ page: 0, pages: 1, start: 0, end: 0 })
  const noop = () => {}
  const html = renderToStaticMarkup(<ActivityPagination page={4} total={27} onPrevious={noop} onNext={noop} />)
  expect(html).toContain('Events 25–27 of 27')
  expect(html.match(/<button[^>]*aria-label="Next events"[^>]*>/)?.[0]).toContain('disabled')
  const cursorPage = renderToStaticMarkup(<ActivityPagination page={0} total={6} hasMore onPrevious={noop} onNext={noop} />)
  expect(cursorPage.match(/<button[^>]*aria-label="Next events"[^>]*>/)?.[0]).not.toContain('disabled')
  expect(cursorPage).not.toContain('of 6')
})

it('keeps unavailable review titles out of links and administrator counts out of member summaries', () => {
  const events: ActivityEntry[] = [
    { event_code: 'document_deleted', outcome: 'completed', document_id: 'unavailable', occurred_at: '2026-10-08T10:00:00Z' },
    { event_code: 'output_copied', outcome: 'completed', document_id: null, occurred_at: '2026-10-08T09:00:00Z' },
    { event_code: 'workspace_rule_saved', outcome: 'failed', document_id: null, occurred_at: '2026-10-07T09:00:00Z' },
  ]
  const html = renderToStaticMarkup(<MemoryRouter><ActivityTimeline events={events} documents={{}} workspaceId="synthetic" asOf="2026-10-08T11:00:00Z" /></MemoryRouter>)
  expect(html).not.toContain('href=')
  expect(html).toContain('Review history')
  expect(html).toContain('is-failed')
  expect(events.filter(event => matchesEvent(event, {}, 'COPIED', 'outputs'))).toEqual([events[1]])
  expect(events.filter(event => matchesEvent(event, {}, '', 'workspace'))).toEqual([events[2]])
  const member = renderToStaticMarkup(<ActivitySummary value={{ own_events: events, own_total: 3, workspace_counts: null,
    since: '2026-09-08T11:00:00Z', as_of: '2026-10-08T11:00:00Z' }} />)
  expect(member).not.toContain('Across your workspace')
  expect(member).not.toContain('Workspace events')
})
