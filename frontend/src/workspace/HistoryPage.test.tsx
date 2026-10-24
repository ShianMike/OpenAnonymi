import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { DocumentHistoryView } from '../api/client'
import type { useHistory } from './history/useHistory'
import { HistoryPage } from './HistoryPage'

const load = vi.hoisted(() => ({ data: {} as ReturnType<typeof useHistory>['data'] }))
vi.mock('./history/useHistory', () => ({ useHistory: () => ({ data: load.data, retry: () => {} }) }))
const history: DocumentHistoryView = {
  document_id: 'document', status: 'draft', created_at: '2026-10-22T12:00:00Z',
  expires_at: '2099-10-23T12:00:00Z', deleted_at: null,
  revision_total: 1, revisions: [{ id: 'one', number: 1, is_current: true, created_at: '2026-10-22T12:00:00Z' }],
  event_total: 3, events: [
    { event_code: 'scan_failed', outcome: 'failed', occurred_at: '2026-10-23T12:00:00Z' },
    { event_code: 'source_revised', outcome: 'completed', occurred_at: '2026-10-23T11:00:00Z' },
    { event_code: 'document_created', outcome: 'completed', occurred_at: '2026-10-22T12:00:00Z' },
  ],
}
function ready(value = history) {
  load.data = { key: 'workspace.document', kind: 'ready', value, checkedAt: '2026-10-23T13:00:00Z' }
}
function render(query = '') {
  return renderToStaticMarkup(<MemoryRouter initialEntries={[{ pathname: '/workspaces/workspace/documents/document/history', search: query, state: { documentsSearch: 'view=favorites&q=Local' } }]}>
    <Routes><Route path="/workspaces/:workspaceId/documents/:documentId/history" element={<HistoryPage />} /></Routes>
  </MemoryRouter>)
}

it('shows date-grouped activity, meaningful outcomes and review context without idle pagination', () => {
  ready()
  const html = render()
  expect(html).toContain('Today')
  expect(html).toContain('Yesterday')
  expect(html).toContain('Suggestions failed')
  expect(html).toContain('class="history-event-outcome" data-outcome="failed"')
  expect(html).toContain('Current version')
  expect(html).toContain('Browse saved versions')
  expect(html).not.toContain('Page 1 of 1')
  expect(html).not.toContain('<table')
  expect(html).toContain('/documents?view=favorites&amp;q=Local&amp;workspace=workspace')
})

it('opens retained activity instead of source controls for expired and deleted reviews', () => {
  for (const status of ['expired', 'deleted'] as const) {
    ready({ ...history, status })
    const html = render('?view=versions')
    expect(html).toContain(status === 'deleted' ? 'This review was deleted' : 'This review has expired')
    expect(html).toContain('Review created')
    expect(html).not.toContain('Open review')
    expect(html).not.toContain('Compare from')
    expect(html).not.toContain('Saved source preview')
    expect(html).not.toContain('Page 1 of 1')
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Versions/)
  }
})

it('previews the only saved version instead of showing an unusable comparison form', () => {
  ready()
  const html = render('?view=versions')
  expect(html).toContain('Saved source preview')
  expect(html).toContain('Loading saved source…')
  expect(html).not.toContain('Swap compared versions')
})

it('bounds activity pages and explains the server history limit', () => {
  ready({ ...history, event_total: 120, events: Array.from({ length: 100 }, () => history.events[0]) })
  const html = render()
  expect(html.match(/<li\b/g)).toHaveLength(12)
  expect(html).toContain('Actions 1–12 of 100')
  expect(html).toContain('Showing the latest 100 of 120 retained actions.')
})

it('replaces previous history with loading or a retry state when access cannot be checked', () => {
  load.data = { key: 'workspace.document', kind: 'error', message: 'Your access changed.' }
  const html = render()
  expect(html).toContain('Your access changed.')
  expect(html).toContain('Try again')
  expect(html).not.toContain('Review created')
  load.data = { key: 'workspace.document', kind: 'loading' }
  expect(render()).toContain('Loading review history…')
})
