import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewSetup } from './ReviewSetup'
import type { ReviewController } from './useReviewController'

const review = { state: { kind: 'ready', saved: { categories: ['email'], phone_region: 'PH', language: 'en', expires_at: '2026-10-30T12:00:00Z' } }, canEdit: true, actionPending: false, dirty: false, settingsDirty: false, conflict: false } as unknown as ReviewController
const render = (value = review, onRenew: (() => void) | undefined = () => {}) => renderToStaticMarkup(<ReviewSetup review={value} onRenew={onRenew} />)

it('offers availability changes only in an editable review with a renewal handler', () => {
  expect(render()).toContain('Extend availability')
  expect(render({ ...review, canEdit: false })).not.toContain('Extend availability')
  expect(renderToStaticMarkup(<ReviewSetup review={review} />)).not.toContain('Extend availability')
  expect(render({ ...review, state: { kind: 'loading' } })).toBe('')
})

it('keeps availability changes disabled until source, settings and conflicts are resolved', () => {
  for (const guard of ['actionPending', 'dirty', 'settingsDirty', 'conflict']) {
    expect(render({ ...review, [guard]: true })).toMatch(/<button[^>]*disabled=""[^>]*>Extend availability<\/button>/)
  }
})
