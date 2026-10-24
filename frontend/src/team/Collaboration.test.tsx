import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import type { HandoffView } from './api'
import { HandoffPanel, ReviewerAccessForm } from './HandoffPanel'
import { FindingDiscussion } from './FindingDiscussion'

const session = { user_id: 'owner', csrf_token: 'synthetic', memberships: [{ workspace_id: 'workspace', role: 'administrator' }] } as SessionView
const handoff: HandoffView = { version: { document_id: 'document', source_revision_id: 'revision', decision_version: 1, settings_version: 1 }, is_owner: true,
  reviewer_id: null, reviewer_email: null, reviewer_active: false,
  require_approval: false, approval_policy: 'owner_choice', approved_at: null, generation: 0 }
const review = { state: { kind: 'ready', saved: { workspace_id: 'workspace', status: 'draft', can_edit: true,
  version: { document_id: 'document', source_revision_id: 'revision', decision_version: 1, settings_version: 1 } } },
  handoff: { value: handoff, error: null, retry: () => {} }, activeFindings: [], codePoints: [], selectedFindingId: null,
  actionPending: false, dirty: false, settingsDirty: false, conflict: false, scan: { status: 'not_started' },
} as unknown as ReviewController
const actions = { busy: false, onBusyChange: () => {}, onSaved: () => {}, onReadOutput: () => {} }
const render = (value: React.ReactNode) => renderToStaticMarkup(<MemoryRouter>{value}</MemoryRouter>)

it('replaces the nested manage dialog with an inline empty state and disables unchanged access', () => {
  const html = render(<ReviewerAccessForm review={review} session={session} handoff={handoff} members={[]} {...actions} />)
  expect(html).toContain('No teammates to assign')
  expect(html).toContain('/members?workspace=workspace')
  expect(html).not.toContain('Manage reviewer')
  expect(html).not.toContain('role="dialog"')
  expect(html).not.toContain('role="combobox"')
  expect(html.match(/<button[^>]*type="submit"[^>]*>/)?.[0]).toContain('disabled=""')
})

it('keeps workspace approval policy enforced in the access form', () => {
  const html = render(<ReviewerAccessForm review={review} session={session} handoff={{ ...handoff, require_approval: true, approval_policy: 'always' }} members={[]} {...actions} />)
  const toggle = html.match(/<input[^>]*role="switch"[^>]*>/)?.[0]
  expect(toggle).toContain('checked=""')
  expect(toggle).toContain('disabled=""')
  expect(html).toContain('Required by workspace policy.')
  expect(html).toContain('Workspace policy')
})

it('explains inactive reviewers without presenting an unrecognized selection', () => {
  const html = render(<ReviewerAccessForm review={review} session={session} handoff={{ ...handoff, reviewer_id: 'inactive', reviewer_email: 'former@example.test' }} members={[]} {...actions} />)
  expect(html).toContain('former@example.test')
  expect(html).toContain('Inactive')
  expect(html).toContain('no longer has active workspace access')
})

it('blocks changes while the document has unsaved edits and limits member management to administrators', () => {
  const html = render(<ReviewerAccessForm review={{ ...review, dirty: true }} session={{ ...session, memberships: [{ workspace_id: 'workspace', role: 'member' }] as SessionView['memberships'] }} handoff={handoff} members={[]} {...actions} />)
  expect(html).toContain('Save your document changes before changing review access.')
  expect(html).toContain('Ask a workspace administrator')
  expect(html).not.toContain('Manage workspace members')
})

it('requires an explicit full-output confirmation before independent approval', () => {
  const assigned = { ...review, state: { kind: 'ready', saved: { ...(review.state.kind === 'ready' ? review.state.saved : {}), status: 'ready', can_edit: false } } } as ReviewController
  const html = render(<HandoffPanel review={assigned} session={session} {...actions} />)
  expect(html).toContain('Read reviewed output')
  expect(html).toContain('I read the full reviewed output and approve this version.')
  expect(html.match(/<button[^>]*>[\s\S]*?<\/button>/g)?.find(button => button.includes('Approve this version'))).toContain('disabled=""')
  expect(html).not.toContain('Reviewer access')
})

it('shows a useful discussion state before any findings exist', () => {
  const html = render(<FindingDiscussion review={review} session={session} active finding="" onFindingChange={() => {}} drafts={{}} onDraftChange={() => {}} busy={false} onBusyChange={() => {}} />)
  expect(html).toContain('No findings to discuss yet')
  expect(html).not.toContain('Choose a finding')
  expect(html).not.toContain('Post comment')
})

it('shows the correct original detail and preserves an escaped unsent draft', () => {
  const points = Array.from('🙂avery@example.test')
  const withFinding = { ...review, codePoints: points, selectedFindingId: 'finding', activeFindings: [{ finding_id: 'finding', category: 'email', span: { start: 1, end: points.length } }] } as ReviewController
  const html = render(<FindingDiscussion review={withFinding} session={session} active finding="finding" onFindingChange={() => {}} drafts={{ finding: { id: 'attempt', text: '<keep this draft>' } }} onDraftChange={() => {}} busy={false} onBusyChange={() => {}} />)
  expect(html).toContain('Original detail')
  expect(html).toContain('avery@example.test')
  expect(html).not.toContain('🙂')
  expect(html).toContain('&lt;keep this draft&gt;')
  expect(html).toContain('Draft kept when you close this panel')
  expect(html).toContain('maxLength="2000"')
  const inactive = render(<FindingDiscussion review={withFinding} session={session} active={false} finding="finding" onFindingChange={() => {}} drafts={{ finding: { id: 'attempt', text: '<keep this draft>' } }} onDraftChange={() => {}} busy={false} onBusyChange={() => {}} />)
  expect(inactive).not.toContain('Loading discussion…')
  expect(inactive).toContain('&lt;keep this draft&gt;')
})
