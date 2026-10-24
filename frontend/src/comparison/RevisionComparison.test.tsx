import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { DocumentHistoryView } from '../api/client'
import { RevisionComparison } from './RevisionComparison'

const history = { document_id: 'example', revision_total: 2, revisions: [
  { id: 'two', number: 2, is_current: true, created_at: '2026-10-23T12:00:00Z' },
  { id: 'one', number: 1, is_current: false, created_at: '2026-10-22T12:00:00Z' },
] } as DocumentHistoryView

it('starts with the previous and current sources selected and a swap control', () => {
  const html = renderToStaticMarkup(<RevisionComparison history={history} />)
  expect(html).toContain('Compare from version 1')
  expect(html).toContain('Version 1 → Version 2')
  expect(html).toContain('Swap compared versions')
  expect(html).toContain('Comparing saved sources…')
  expect(html).not.toContain('type="submit"')
  expect(html).not.toContain('Page 1 of 1')
})

it('explains how to create a version when none exist, without empty controls', () => {
  const html = renderToStaticMarkup(<RevisionComparison history={{ ...history, revisions: [], revision_total: 0 }} />)
  expect(html).toContain('No saved versions yet')
  expect(html).not.toContain('Compare from')
  expect(html).not.toContain('Saved versions contain original')
})
