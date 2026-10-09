import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { StyleControls } from './StyleControls'
import { createReviewDecisionActions } from './reviewDecisionActions'
import type { ReviewController } from './useReviewController'
import type { ReviewFinding } from './textSegments'

it('shows only relevant options and requires an explicit keep reason while preserving save guards', () => {
  const finding = { finding_id: 'email', category: 'email', action: null, keep_reason: null } as ReviewFinding
  const review = {
    state: { kind: 'ready', saved: { version: { decision_version: 1 }, csv: null, category_defaults: {}, preferred_action: 'label' } },
    pendingDecisionIds: [], groupMembers: new Map(),
  } as unknown as ReviewController
  const render = (item = finding, value = review) => renderToStaticMarkup(<StyleControls finding={item} review={value} onApplied={() => {}} />)
  const save = (markup: string) => markup.match(/<button\b[^>]*>Save choice<\/button>/)?.[0]
  expect(render()).toContain('Replacement style')
  expect(render()).not.toContain('Why keep this detail?')
  expect(render()).not.toContain('Decision action')
  expect(save(render())).not.toContain('disabled')
  const kept = { ...finding, action: 'keep' as const }
  expect(render(kept)).not.toContain('Replacement style')
  expect(render(kept)).toContain('Choose why this detail can stay before saving.')
  expect(save(render(kept))).toContain('disabled')
  expect(save(render({ ...kept, keep_reason: 'intended_disclosure' }))).not.toContain('disabled')
  expect(save(render({ ...kept, keep_reason: 'unknown' }))).toContain('disabled')
  expect(save(render(finding, { ...review, conflict: true }))).toContain('disabled')
  expect(render(finding, { ...review, pendingDecisionIds: ['email'] })).toContain('Saving choice')
})

it('keeps the chosen reason bound to the confirmed group and rejects a changed group', () => {
  const version = { document_id: 'doc', source_revision_id: 'source', decision_version: 1, settings_version: 1 }
  const members = ['first', 'second'].map((finding_id, start) => ({ finding_id, group_id: 'group', category: 'email', span: { start, end: start + 1 } }))
  const enqueueDecision = vi.fn(() => true)
  const setError = vi.fn()
  const options = {
    documentId: 'doc', state: { kind: 'ready', saved: { version } },
    findings: { version, findings: members },
    keepReason: 'false_match',
    groupConfirmation: {
      findingId: 'first', action: 'keep', keepReason: 'intended_disclosure',
      choice: { style: 'token', style_option: null },
      affectedIds: ['first', 'second'], spans: members.map((item) => item.span), version,
    },
    enqueueDecision, setGroupConfirmation: () => {}, setError,
  } as unknown as Parameters<typeof createReviewDecisionActions>[0]
  createReviewDecisionActions(options).confirmGroupDecision()
  expect(enqueueDecision).toHaveBeenCalledWith(options.findings, expect.objectContaining({
    keepReason: 'intended_disclosure', groupScope: true, ids: ['first', 'second'],
  }))
  enqueueDecision.mockClear()
  createReviewDecisionActions({ ...options, findings: { ...options.findings!, findings: options.findings!.findings.slice(0, 1) } }).confirmGroupDecision()
  expect(enqueueDecision).not.toHaveBeenCalled()
  expect(setError).toHaveBeenCalledWith(expect.stringContaining('This group changed'))
})
