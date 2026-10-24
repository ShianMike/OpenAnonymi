import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { SourceConflictRecovery } from './SourceConflictRecovery'
import type { ReviewController } from './useReviewController'

const review = {
  conflict: true, dirty: true, text: 'My unsaved <draft>', actionPending: false,
  sourceRecovery: { comparison: { saved: { text: 'The saved <source>' } }, pending: false, error: null },
} as unknown as ReviewController

it('shows both sources as escaped text and keeps the replacement consequence visible', () => {
  const html = renderToStaticMarkup(<SourceConflictRecovery review={review} />)
  expect(html).toContain('My unsaved &lt;draft&gt;')
  expect(html).toContain('The saved &lt;source&gt;')
  expect(html).toContain('aria-labelledby="local-source-title"')
  expect(html).toContain('aria-labelledby="latest-source-title"')
  expect(html).toContain('reset its findings and review confirmation')
  expect(html).toContain('Continue with my edits')
  expect(html).toContain('Cancel comparison')
  for (const changes of [{ conflict: false }, { dirty: false }]) {
    expect(renderToStaticMarkup(<SourceConflictRecovery review={{ ...review, ...changes }} />)).toBe('')
  }
})

it('prevents repeat refreshes while loading and keeps retry errors visible', () => {
  const html = renderToStaticMarkup(<SourceConflictRecovery review={{ ...review, sourceRecovery: { ...review.sourceRecovery, comparison: null, pending: true, error: 'Could not load this version.' } }} />)
  expect(html).toMatch(/<button[^>]*disabled=""/)
  expect(html).toContain('Loading latest version…')
  expect(html).toContain('role="alert">Could not load this version.')
  expect(html).toContain('Your edits are still here.')
})
