import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { DocumentIndexView } from '../../api/client'
import { DocumentGallery } from './DocumentGallery'

it('keeps the 50-review selection limit and prevents opening a review after expiry', () => {
  const now = Date.parse('2026-10-08T00:00:00Z')
  const items = Array.from({ length: 51 }, (_, index) => ({
    id: `review-${index}`, title: `Review ${index}`, is_owner: true,
    status: 'needs_review', finding_count: 1, decided_count: 0,
    created_at: '2026-10-07T00:00:00Z', updated_at: '2026-10-07T00:00:00Z',
    expires_at: '2026-10-10T00:00:00Z', current_revision_id: 'revision', favorite: false, pinned: false,
  } as DocumentIndexView))
  const expired = { ...items[0], id: 'expired-review', title: 'Must not appear after expiry', expires_at: '2026-10-07T00:00:00Z' }
  const selected = new Set(items.slice(0, 50).map(item => item.id))
  const noop = () => {}
  const html = renderToStaticMarkup(<MemoryRouter><DocumentGallery items={[...items, expired]}
    workspaceId="fixture" search="workspace=fixture&view=in_progress" now={now} selected={selected} selecting={true} pending={false} preferencePending={new Set()}
    onDelete={noop} onSelect={noop} onPreference={noop} onRenew={noop} />
  </MemoryRouter>)
  const inputs = html.match(/<input\b[^>]*>/g)!
  expect(inputs.find(input => input.includes('Select Review 0'))).not.toContain('disabled')
  expect(inputs.find(input => input.includes('Select Review 50'))).toContain('disabled')
  expect(html).toContain('class="document-gallery"')
  expect(html).not.toContain('<table')
  expect(html).not.toContain('Must not appear after expiry')
  expect(html).not.toContain('href="/documents/expired-review/edit"')
  expect(html).not.toContain('href="/documents/review-0/edit"')
  expect(html).not.toContain('Actions for Review 0')
  expect(html).toContain('Content is no longer available')
})

it('keeps browsing free of selection controls and preserves the document link and review description', () => {
  const item = { id: 'review', title: 'Fictional review', status: 'needs_review', is_owner: true,
    current_revision_id: 'revision', expires_at: '2099-01-01T00:00:00Z',
    created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', finding_count: 2, decided_count: 1,
  } as DocumentIndexView
  const noop = () => {}
  const html = renderToStaticMarkup(<MemoryRouter><DocumentGallery items={[item]} workspaceId="fixture" search=""
    now={Date.parse('2026-10-21T00:00:00Z')} selected={new Set()} selecting={false} pending={false} preferencePending={new Set()}
    onDelete={noop} onSelect={noop} onPreference={noop} onRenew={noop} /></MemoryRouter>)
  expect(html).not.toContain('type="checkbox"')
  expect(html).toContain('href="/documents/review/edit"')
  expect(html).toContain('Actions for Fictional review')
  expect(html).toContain('aria-describedby="document-review-review"')
})
