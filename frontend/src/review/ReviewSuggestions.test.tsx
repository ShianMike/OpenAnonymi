import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewSuggestions } from './ReviewSuggestions'
import type { ReviewController } from './useReviewController'

it('keeps scanning gated by saved changes and ownership, and shows refresh only after a scan starts', () => {
  const review = {
    state: { kind: 'ready', saved: {
      version: { source_revision_id: 'revision', settings_version: 1 },
      categories: ['email', 'phone'], csv: null, preset_id: null,
      phone_region: 'US', language: 'en', expires_at: '2026-10-15T12:00:00Z',
    } },
    canEdit: true, dirty: false, settingsDirty: false, actionPending: false, conflict: false,
    scan: { status: 'not_started', match_count: 0, dropped_suggestions: 0, suggestions: [] },
  } as unknown as ReviewController
  const render = (value: ReviewController) => renderToStaticMarkup(<ReviewSuggestions review={value} />)
  const button = (html: string, text: string) => html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)?.find(item => item.includes(text))
  const initial = render(review)
  expect(button(initial, 'Find suggestions')).not.toContain('disabled=""')
  expect(initial).not.toContain('aria-label="Refresh scan status"')
  expect(initial).toContain('Email addresses')
  expect(initial).toContain('Other categories won’t be scanned.')
  for (const blocked of [{ dirty: true }, { settingsDirty: true }, { conflict: true }, { actionPending: true }]) {
    expect(button(render({ ...review, ...blocked }), 'Find suggestions')).toContain('disabled=""')
  }
  const scanning = render({ ...review, scan: { ...review.scan!, status: 'scanning' } })
  expect(button(scanning, 'Scanning…')).toContain('disabled=""')
  expect(scanning).toContain('aria-label="Refresh scan status"')
  const completed = render({ ...review, scan: { ...review.scan!, status: 'completed' } })
  expect(completed).not.toContain('Find suggestions')
  expect(completed).toContain('No suggestions found. Review the full text before sharing.')
  const reader = render({ ...review, canEdit: false })
  expect(reader).not.toContain('Find suggestions')
  expect(reader).not.toContain('aria-label="Change detection categories"')
  expect(reader).toContain('The owner runs suggestions.')
})
