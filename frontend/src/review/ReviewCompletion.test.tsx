import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewCompletionBody } from './ReviewCompletion'
import type { ReviewController } from './useReviewController'

it('explains the next step while confirmation and approval still gate sharing', () => {
  const review = {
    state: { kind: 'ready', saved: { status: 'draft', version: {}, csv: null } },
    canEdit: true, canConfirm: false, canExport: false,
    scan: { status: 'not_started' }, pendingFindings: [], findings: { overlaps: [] },
    handoff: { value: null, exportApproved: true },
    confirmedPreview: false, setConfirmedPreview: () => {},
  } as unknown as ReviewController
  const render = (value: ReviewController) => renderToStaticMarkup(<ReviewCompletionBody review={value} />)
  const button = (markup: string, label: string) => markup.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)?.find((item) => item.includes(label))
  const draft = render(review)
  expect(draft).toContain('Find suggestions first')
  expect(button(draft, 'Confirm review')).toContain('disabled=""')
  expect(button(draft, 'Copy reviewed text')).toContain('disabled=""')
  expect(draft).not.toContain('studio-read-output')
  expect(draft).toContain('Confirmation required')
  const complete = { ...review, scan: { ...review.scan!, status: 'completed' as const } }
  expect(render({ ...complete, pendingFindings: [{}] as ReviewController['pendingFindings'] })).toContain('1 detail needs your choice')
  expect(render({ ...complete, canConfirm: true })).toContain('studio-read-output')
  expect(render({ ...complete, canConfirm: true })).toContain('Preview output')
  expect(render({ ...complete, settingsDirty: true })).toContain('Save your suggestion settings')
  const approvedState = { kind: 'ready' as const, saved: { ...(review.state.kind === 'ready' ? review.state.saved : {}), status: 'ready' as const } }
  const locked = render({ ...complete, state: approvedState as ReviewController['state'], handoff: { ...review.handoff, exportApproved: false } })
  expect(locked).toContain('Waiting for approval')
  expect(locked).not.toContain('Ready to share')
  expect(button(locked, 'Prepare download')).toContain('disabled=""')
  const unlocked = render({ ...complete, state: approvedState as ReviewController['state'], canExport: true })
  expect(unlocked).toContain('Ready to share')
  expect(unlocked).toContain('Prepare the file, then save it to your device.')
  expect(button(unlocked, 'Copy reviewed text')).not.toContain('disabled=""')
  expect(button(unlocked, 'Prepare download')).not.toContain('disabled=""')
  const preparing = render({ ...complete, state: approvedState as ReviewController['state'], exportPending: true, actionPending: true })
  expect(preparing).toContain('Preparing output')
  expect(preparing).not.toContain('Waiting for approval')
  expect(unlocked).not.toContain('Excel')
})

const version = { document_id: 'document', source_revision_id: 'revision', decision_version: 2, settings_version: 1 }
const confirmed = {
  state: { kind: 'ready', saved: { title: 'Fictional review', status: 'ready', file_format: 'txt', version, csv: null } },
  canEdit: true, canConfirm: false, canExport: true, scan: { status: 'completed' },
  pendingFindings: [], findings: { overlaps: [] }, handoff: { value: null, exportApproved: true },
} as unknown as ReviewController
const render = (review: ReviewController) => renderToStaticMarkup(<ReviewCompletionBody review={review} />)
const choice = (html: string, value: string) => html.match(/<input\b[^>]*>/g)?.find(input => input.includes(`value="${value}"`))

it('offers the four supported output formats without CSV controls', () => {
  const text = render(confirmed)
  expect(text.match(/type="radio"/g)).toHaveLength(4)
  expect(choice(text, 'txt')).toContain('checked=""')
  expect(text).toContain('Text with exact spacing')
  expect(text).toContain('Preserves tabs, spaces and line endings')
  expect(text).not.toContain('value="csv"')
  const pdf = render({ ...confirmed, state: { kind: 'ready', saved: { ...(confirmed.state.kind === 'ready' ? confirmed.state.saved : {}), file_format: 'pdf' } } as ReviewController['state'] })
  expect(choice(pdf, 'pdf')).toContain('checked=""')
  expect(pdf).toContain('the PDF is not searchable')
  expect(pdf).toContain('Original text layers, attachments, forms and annotations are removed')

})

it('offers a Save link only for the selected format and exact version', () => {
  const preparedDownload = { url: 'blob:synthetic', filename: 'reviewed.txt', format: 'txt' as const, version }
  const ready = render({ ...confirmed, preparedDownload })
  expect(ready).toContain('href="blob:synthetic" download="reviewed.txt"')
  expect(ready).toContain('Save TXT')
  expect(ready).not.toContain('Prepare download')
  for (const review of [
    { ...confirmed, preparedDownload: { ...preparedDownload, version: { ...version, decision_version: 1 } } },
    { ...confirmed, preparedDownload: { ...preparedDownload, format: 'pdf' as const } },
    { ...confirmed, preparedDownload, canExport: false },
    { ...confirmed, preparedDownload, exportPending: true },
  ]) {
    const html = render(review)
    expect(html).not.toContain('href="blob:synthetic"')
  }

})

it('presents decision totals, applied styles and distinct confirmation and export times', () => {
  const currentSummary = {
    version, finding_count: 2, counts_by_action: { label: 1, redact: 1 },
    counts_by_action_and_style: { label: { token: 1 }, redact: { token: 1 } },
    fictional_replacements: 0, confirmed_at: '2026-10-24T03:00:00Z', last_output_generated_at: '2026-10-24T03:05:00Z',
  } as unknown as NonNullable<ReviewController['currentSummary']>
  const html = render({ ...confirmed, currentSummary })
  expect(html).toContain('aria-label="Decisions in this version"')
  expect(html).toContain('<dt>Replaced</dt><dd>1</dd>')
  expect(html).toContain('<dt>Hidden</dt><dd>1</dd>')
  expect(html).toContain('<dt>Kept</dt><dd>0</dd>')
  expect(html).toContain('Category labels')
  expect(html).toContain('Hidden with [REDACTED]')
  expect(html).toContain('<dt>Output prepared</dt>')
  expect(html).toMatch(/datetime="2026-10-24T03:05:00Z"/i)
  expect(render({ ...confirmed, currentSummary, dirty: true })).not.toContain('Decisions in this version')
  const empty = render({ ...confirmed, currentSummary: { ...currentSummary, finding_count: 0, counts_by_action: {}, counts_by_action_and_style: {} } })
  expect(empty).toContain('No findings were marked.')
  expect(empty).not.toContain('Applied styles')
})
