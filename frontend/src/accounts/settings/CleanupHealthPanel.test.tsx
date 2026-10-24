import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { CleanupHealthView } from '../../api/client'
import { CleanupStatus } from './CleanupHealthPanel'

const health: CleanupHealthView = { checked_at: '2026-10-23T11:00:00Z', last_success_at: '2026-10-23T10:00:00Z',
  last_failure_at: '2026-10-22T11:00:00Z', overdue: false, documents_awaiting_purge: 2 }

it('distinguishes current service health from historical failures and scopes the purge count', () => {
  const html = renderToStaticMarkup(<CleanupStatus health={health} />)
  expect(html).toContain('Cleanup is up to date')
  expect(html).toContain('1 hour ago')
  expect(html).toContain('Last recorded failure:')
  expect(html).toContain('1 day ago')
  expect(html).toContain('reviews in this workspace are')
  expect(html).not.toContain('Ask your service operator')
})

it('does not show a healthy status when no completed cleanup is recorded', () => {
  const html = renderToStaticMarkup(<CleanupStatus health={{ ...health, overdue: true, last_success_at: null, last_failure_at: null, documents_awaiting_purge: 1 }} />)
  expect(html).toContain('Cleanup needs attention')
  expect(html).toContain('No completed cleanup has been recorded yet')
  expect(html).toContain('Ask your service operator')
  expect(html).toContain('review in this workspace is')
  expect(html).not.toContain('Cleanup is up to date')
})
