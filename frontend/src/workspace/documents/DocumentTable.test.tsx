import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { DocumentIndexView } from '../../api/client'
import { DocumentTable } from './DocumentTable'

it('keeps the 50-review selection limit and prevents opening a review after expiry', () => {
  const now = Date.parse('2026-10-08T00:00:00Z')
  const items = Array.from({ length: 51 }, (_, index) => ({
    id: `review-${index}`, title: `Review ${index}`, is_owner: true,
    status: 'needs_review', finding_count: 1, decided_count: 0,
    created_at: '2026-10-07T00:00:00Z', updated_at: '2026-10-07T00:00:00Z',
    expires_at: '2026-10-10T00:00:00Z', favorite: false, pinned: false,
  } as DocumentIndexView))
  const expired = { ...items[0], id: 'expired-review', title: null, expires_at: '2026-10-07T00:00:00Z' }
  const selected = new Set(items.slice(0, 50).map(item => item.id))
  const noop = () => {}
  const html = renderToStaticMarkup(<MemoryRouter><DocumentTable items={[...items, expired]}
    workspaceId="fixture" now={now} selected={selected} pending={false} preferencePending={new Set()}
    onDelete={noop} onSelect={noop} onSelectVisible={noop} onPreference={noop} onRenew={noop} />
  </MemoryRouter>)
  const inputs = html.match(/<input\b[^>]*>/g)!
  expect(inputs.find(input => input.includes('Select Review 0'))).not.toContain('disabled')
  expect(inputs.find(input => input.includes('Select Review 50'))).toContain('disabled')
  expect(inputs.find(input => input.includes('id="document-select-visible"'))).toContain('checked')
  expect(html).not.toContain('href="/documents/expired-review/edit"')
  expect(html).toContain('Unavailable')
})
