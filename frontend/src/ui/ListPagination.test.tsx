import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { DocumentIndexView, SessionView } from '../api/client'
import { AccountPanel } from '../accounts/settings/AccountPanel'
import { ReviewQueueList } from '../resume/ReviewQueueList'
import { ListPagination } from './ListPagination'
import { pageWindow } from './pagination'

it('reaches every item once without extending the page, including empty and shrinking lists', () => {
  for (const pageSize of [3, 4, 5, 6]) {
    const items = Array.from({ length: 36 }, (_, index) => index)
    const visited = Array.from({ length: Math.ceil(items.length / pageSize) }, (_, page) => {
      const range = pageWindow(items.length, page, pageSize)
      return items.slice(range.start, range.end)
    }).flat()
    expect(visited).toEqual(items)
    expect(pageWindow(1, 9, pageSize)).toEqual({ page: 0, pages: 1, start: 0, end: 1 })
    expect(pageWindow(0, -1, pageSize)).toEqual({ page: 0, pages: 1, start: 0, end: 0 })
  }
  const noop = () => {}
  const last = renderToStaticMarkup(<ListPagination label="Updates" total={36} page={7} pageSize={5} onPrevious={noop} onNext={noop} />)
  expect(last).toContain('Updates 36–36 of 36')
  expect(last.match(/<button[^>]*aria-label="Next updates"[^>]*>/)?.[0]).toContain('disabled')
  const cursor = renderToStaticMarkup(<ListPagination label="Updates" total={50} page={9} pageSize={5} hasMore onPrevious={noop} onNext={noop} />)
  expect(cursor.match(/<button[^>]*aria-label="Next updates"[^>]*>/)?.[0]).not.toContain('disabled')
  expect(cursor).not.toContain('of 50')
})

it('bounds workspace and review cards when the account and queue have many items', () => {
  const memberships = Array.from({ length: 25 }, (_, index) => ({
    workspace_id: `workspace-${index}`, workspace_name: `Workspace ${index}`, role: index ? 'member' as const : 'administrator' as const,
    require_second_factor: false,
  }))
  const session = { user_id: 'synthetic', email: 'test@example.test', csrf_token: 'synthetic', memberships,
    email_verified: false, email_verification_available: false, second_factor_enabled: false } as SessionView
  const account = renderToStaticMarkup(<MemoryRouter><AccountPanel session={session} onSessionChanged={() => {}} /></MemoryRouter>)
  expect(account).toContain('Workspaces 1–3 of 25')
  expect(account.match(/aria-label="Open Workspace /g)).toHaveLength(3)
  expect(account).toContain('aria-label="Find a workspace"')
  expect(account).toContain('Administrator')
  expect(account).toContain('Member')
  const now = Date.parse('2026-10-08T12:00:00Z')
  const reviews = memberships.map((_, index) => ({ id: `review-${index}`, title: `Shared review ${index}`,
    status: 'needs_review', finding_count: 3, decided_count: 1, updated_at: '2026-10-08T11:00:00Z',
    is_owner: false } as DocumentIndexView))
  const queue = renderToStaticMarkup(<MemoryRouter><ReviewQueueList items={reviews} assigned now={now} workspaceId="workspace-0" /></MemoryRouter>)
  expect(queue).toContain('Reviews 1–3 of 25')
  expect(queue.match(/aria-label="Open Shared review /g)).toHaveLength(3)
  expect(queue).toContain('aria-label="Find a shared review"')
  expect(queue).not.toContain('Show more')
})
