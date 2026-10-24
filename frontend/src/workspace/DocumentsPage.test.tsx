import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { DocumentIndexView, SessionView } from '../api/client'
import { DocumentsPage } from './DocumentsPage'

const load = vi.hoisted(() => ({ value: {} as { kind: string; items?: DocumentIndexView[]; message?: string } }))
vi.mock('./documents/useDocuments', () => ({ useDocuments: () => ({ data: load.value, retry: () => {}, updateItems: () => {} }) }))
const session = { user_id: 'synthetic', csrf_token: 'synthetic', memberships: [
  { workspace_id: 'workspace', workspace_name: 'Fictional workspace', role: 'member' },
] } as SessionView
const item = { id: 'assigned', title: 'Fictional shared review', is_owner: false, status: 'ready',
  current_revision_id: 'revision', finding_count: 2, decided_count: 2, favorite: false, pinned: false,
  created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-21T00:00:00Z', expires_at: '2099-10-30T00:00:00Z' } as DocumentIndexView
const render = (query = '') => renderToStaticMarkup(<MemoryRouter initialEntries={['/documents?workspace=workspace' + query]}><DocumentsPage session={session} /></MemoryRouter>)

it('offers shared work in the document gallery with its approval step and a single Documents view', () => {
  load.value = { kind: 'ready', items: [item] }
  const html = render('&view=shared')
  expect(html).toContain('role="tablist"')
  expect(html).toContain('aria-label="Document views"')
  expect(html).toContain('Open Fictional shared review')
  expect(html).toContain('Read and approve the output.')
  expect(html).toContain('class="document-gallery"')
  expect(html).not.toContain('<table')
  expect(html).not.toContain('href="/continue')
  expect(html).toContain('id="document-select-mode"')
  expect(html).toContain('aria-pressed="false"')
  expect(html).not.toContain('type="checkbox"')
})

it('bounds long lists to a page and preserves URL search and page state', () => {
  load.value = { kind: 'ready', items: Array.from({ length: 61 }, (_, index) => ({ ...item, id: String(index), title: `Fictional review ${index}` })) }
  const html = render('&page=2&q=Fictional')
  expect(html).toContain('Documents 51–61 of 61')
  expect(html.match(/aria-label="Open Fictional review /g)).toHaveLength(11)
  expect(html).toContain('value="Fictional"')
})

it('replaces actionable titles with a retry state on an access or network failure', () => {
  load.value = { kind: 'error', message: 'Your access changed.' }
  const html = render()
  expect(html).toContain('Documents couldn’t be loaded')
  expect(html).toContain('Your access changed.')
  expect(html).toContain('Try again')
  expect(html).not.toContain('Fictional shared review')
  load.value = { kind: 'loading' }
  const loading = render()
  expect(loading).toContain('Loading your documents…')
  expect(loading).toContain('loading-skeleton-gallery')
  expect(loading).not.toContain('All documents<span>0</span>')
})

it('provides relevant empty states for shared work, unfinished work, favorites and searches', () => {
  load.value = { kind: 'ready', items: [] }
  expect(render('&view=shared')).toContain('Nothing shared with you yet')
  expect(render('&view=in_progress')).toContain('You’re all caught up')
  expect(render('&view=favorites')).toContain('Keep your go-to documents here')
  expect(render('&q=missing')).toContain('No matching documents')
})
