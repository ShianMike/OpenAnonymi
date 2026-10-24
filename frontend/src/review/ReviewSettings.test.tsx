import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewSettings } from './ReviewSettings'
import type { ReviewController } from './useReviewController'

it('summarizes settings without exposing a second form, and retains pending and unsaved states', () => {
  const review = { state: { kind: 'ready', saved: { version: { source_revision_id: 'synthetic', settings_version: 1 } } }, settingsOpen: false,
    emailEnabled: true, phoneEnabled: true, extraCategories: [],
    settingsDirty: false, actionPending: false } as unknown as ReviewController
  const render = (value: ReviewController) => renderToStaticMarkup(<ReviewSettings review={value} csrf="synthetic" />)
  const saved = render(review)
  expect(saved).toContain('id="review-suggestion-settings"')
  expect(saved).toContain('aria-haspopup="dialog"')
  expect(saved).toContain('2 categories')
  expect(saved).not.toContain('id="review-email"')
  expect(render({ ...review, settingsDirty: true })).toContain('Unsaved changes')
  expect(render({ ...review, actionPending: true })).toContain('disabled=""')
  expect(render({ ...review, state: { kind: 'loading' } })).toBe('')
})
