import { describe, expect, it } from 'vitest'
import type { DocumentIndexView } from '../api/client'
import { reviewQueue } from './reviewQueue'

const now = Date.parse('2026-10-01T12:00:00Z')
function item(id: string, changes: Partial<DocumentIndexView> = {}): DocumentIndexView {
  return { id, is_owner: true, title: 'Fictional review', status: 'needs_review',
    created_at: '2026-10-01T09:00:00Z', updated_at: '2026-10-01T10:00:00Z',
    expires_at: '2026-10-08T09:00:00Z', current_revision_id: 'revision', finding_count: 3,
    decided_count: 1, favorite: false, pinned: false, ...changes }
}

describe('available reviews to continue', () => {
  it('never offers expired, deleted, missing-revision or malformed-expiry content, even as the last review', () => {
    const records = [item('elapsed', { expires_at: '2026-10-01T11:59:59Z' }),
      item('boundary', { expires_at: '2026-10-01T12:00:00Z' }),
      item('expired', { status: 'expired' }), item('deleted', { status: 'deleted' }),
      item('missing', { current_revision_id: null }), item('invalid', { expires_at: 'invalid' })]
    const queue = reviewQueue(records, 'elapsed', now)
    expect(queue.last).toBeNull()
    expect(queue.assigned).toEqual([])
    expect(queue.unfinished).toEqual([])
  })
  it('separates ownership from review assignment and keeps confirmed assigned work accessible', () => {
    const mine = item('mine')
    const assignment = item('assignment', { is_owner: false, status: 'ready' })
    const confirmed = item('confirmed', { status: 'ready' })
    const queue = reviewQueue([mine, assignment, confirmed], 'assignment', now)
    expect(queue.assigned).toEqual([assignment])
    expect(queue.unfinished).toEqual([mine])
    expect(queue.last).toEqual(assignment)
    expect(reviewQueue([confirmed], 'confirmed', now).last).toEqual(confirmed)
  })
  it('does not substitute another document for a missing or revoked last document', () => {
    expect(reviewQueue([item('mine')], 'revoked', now).last).toBeNull()
    expect(reviewQueue([item('mine')], null, now).last).toBeNull()
  })
  it('prioritizes recently updated work without mutating the authorized index', () => {
    const older = item('older')
    const newer = item('newer', { updated_at: '2026-10-01T11:00:00Z' })
    const records = [older, newer]
    expect(reviewQueue(records, null, now).unfinished).toEqual([newer, older])
    expect(records).toEqual([older, newer])
  })
})
