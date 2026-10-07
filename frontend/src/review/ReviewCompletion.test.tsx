import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewCompletion } from './ReviewCompletion'
import type { ReviewController } from './useReviewController'

it('explains the next step while confirmation and approval still gate sharing', () => {
  const review = {
    state: { kind: 'ready', saved: { status: 'draft', version: {}, csv: null } },
    canEdit: true, canConfirm: false, canExport: false,
    scan: { status: 'not_started' }, pendingFindings: [], findings: { overlaps: [] },
    handoff: { value: null, exportApproved: true },
    confirmedPreview: false, setConfirmedPreview: () => {},
  } as unknown as ReviewController
  const render = (value: ReviewController) => renderToStaticMarkup(<ReviewCompletion review={value} />)
  const button = (markup: string, label: string) => markup.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)?.find((item) => item.includes(label))
  const draft = render(review)
  expect(draft).toContain('Find suggestions first')
  expect(button(draft, 'Confirm review')).toContain('disabled=""')
  expect(button(draft, 'Copy reviewed text')).toContain('disabled=""')
  expect(draft).not.toContain('completion-read')
  const complete = { ...review, scan: { ...review.scan!, status: 'completed' as const } }
  expect(render({ ...complete, pendingFindings: [{}] as ReviewController['pendingFindings'] })).toContain('1 detail needs your choice')
  expect(render({ ...complete, canConfirm: true })).toContain('completion-read')
  expect(render({ ...complete, settingsDirty: true })).toContain('Save your suggestion settings')
  const approvedState = { kind: 'ready' as const, saved: { ...(review.state.kind === 'ready' ? review.state.saved : {}), status: 'ready' as const } }
  const locked = render({ ...complete, state: approvedState as ReviewController['state'], handoff: { ...review.handoff, exportApproved: false } })
  expect(locked).toContain('Waiting for approval')
  expect(locked).not.toContain('Your reviewed version is ready')
  expect(button(locked, 'Generate reviewed TXT')).toContain('disabled=""')
  const unlocked = render({ ...complete, state: approvedState as ReviewController['state'], canExport: true })
  expect(unlocked).toContain('Your reviewed version is ready')
  expect(unlocked).toContain('use its Save link')
  expect(button(unlocked, 'Copy reviewed text')).not.toContain('disabled=""')
  expect(button(unlocked, 'Generate reviewed TXT')).not.toContain('disabled=""')
})
