import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { DocumentIndexView, MemberView } from '../../api/client'
import type { HandoffView } from '../../team/api'
import { ReviewAssignmentDetails } from './MemberReviewAssignment'
import { assignableReviews } from './memberPresentation'

const now = Date.parse('2026-10-23T08:00:00Z')
function review(id: string, changes: Partial<DocumentIndexView> = {}): DocumentIndexView {
  return { id, title: id, is_owner: true, status: 'needs_review', current_revision_id: 'revision',
    created_at: '2026-10-20T08:00:00Z', updated_at: '2026-10-23T07:00:00Z', expires_at: '2026-10-30T08:00:00Z',
    finding_count: 3, decided_count: 1, favorite: false, pinned: false, ...changes }
}

it('offers only owned reviews with available source content and no scan in progress', () => {
  const reviews = [review('draft', { status: 'draft' }), review('ready', { status: 'ready' }), review('exported', { status: 'exported' }),
    review('scan', { status: 'scanning' }), review('shared', { is_owner: false }), review('missing', { current_revision_id: null }),
    review('expired', { status: 'expired' }), review('deleted', { status: 'deleted' }), review('elapsed', { expires_at: '2026-10-23T08:00:00Z' })]
  expect(assignableReviews(reviews, '', now).map(item => item.id)).toEqual(['draft', 'exported', 'ready'])
  expect(reviews).toHaveLength(9)
})

it('searches titles without exposing expired titles and sorts recent reviews first without mutating the list', () => {
  const reviews = [review('old', { title: 'Team report' }), review('new', { title: 'TEAM report', updated_at: '2026-10-23T07:30:00Z' }),
    review('elapsed', { title: 'Private canary', expires_at: '2026-10-23T08:00:00Z' })]
  expect(assignableReviews(reviews, ' TEAM ', now).map(item => item.id)).toEqual(['new', 'old'])
  expect(assignableReviews(reviews, 'canary', now)).toEqual([])
  expect(reviews.map(item => item.id)).toEqual(['old', 'new', 'elapsed'])
})

it('explains original-content access, owner-only controls, and replacement of an existing reviewer', () => {
  const member: MemberView = { user_id: 'new', email: 'nora@example.invalid', role: 'member', revoked_at: null, disabled_at: null }
  const handoff: HandoffView = { version: { document_id: 'doc', source_revision_id: 'rev', decision_version: 0, settings_version: 0 },
    is_owner: true, reviewer_id: 'previous', reviewer_email: 'alex@example.invalid', reviewer_active: true, require_approval: false, approved_at: null, generation: 1, approval_policy: 'owner_choice' }
  const html = renderToStaticMarkup(<ReviewAssignmentDetails member={member} handoff={handoff} />)
  expect(html).toContain('can read original content, make decisions, comment and approve')
  expect(html).toContain('You control source edits and exports')
  expect(html).toContain('This replaces alex@example.invalid')
  expect(renderToStaticMarkup(<ReviewAssignmentDetails member={member} handoff={{ ...handoff, reviewer_id: member.user_id }} />)).not.toContain('This replaces')
})
