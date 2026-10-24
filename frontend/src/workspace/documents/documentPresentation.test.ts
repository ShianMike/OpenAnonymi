import { describe, expect, it } from 'vitest'
import type { DocumentIndexView } from '../../api/client'
import { currentDocuments, readDocumentQuery, visibleDocuments } from './documentPresentation'
import { pageWindow } from '../../ui/pagination'

const now = Date.parse('2026-10-23T08:00:00Z')
function document(id: string, changes: Partial<DocumentIndexView> = {}): DocumentIndexView {
  return { id, title: id, is_owner: true, status: 'needs_review', current_revision_id: 'revision',
    created_at: '2026-10-20T08:00:00Z', updated_at: '2026-10-23T07:00:00Z',
    expires_at: '2026-10-30T08:00:00Z', finding_count: 3, decided_count: 1,
    favorite: false, pinned: false, ...changes }
}
const query = (value: string) => readDocumentQuery(new URLSearchParams(value))

describe('unified document views', () => {
  const records = [document('draft', { status: 'draft' }), document('review'),
    document('failed', { status: 'failed' }), document('scan', { status: 'scanning' }),
    document('ready', { status: 'ready' }), document('export', { status: 'exported', favorite: true }),
    document('assigned', { is_owner: false }), document('assigned-ready', { is_owner: false, status: 'ready' }),
    document('expired', { status: 'expired', favorite: true }), document('deleted', { status: 'deleted' })]
  const current = currentDocuments(records, now)
  it('merges unfinished drafts, failed scans, active work and review assignments without losing completed assignments', () => {
    expect(visibleDocuments(current, query('view=in_progress')).map(item => item.id).sort()).toEqual(['draft', 'failed', 'review', 'scan'])
    expect(visibleDocuments(current, query('view=shared')).map(item => item.id).sort()).toEqual(['assigned', 'assigned-ready'])
    expect(visibleDocuments(current, query('view=completed')).map(item => item.id).sort()).toEqual(['assigned-ready', 'export', 'ready'])
    expect(visibleDocuments(current, query('view=favorites')).map(item => item.id)).toEqual(['export'])
    expect(visibleDocuments(current, query('')).map(item => item.id)).not.toContain('deleted')
  })
  it('removes elapsed titles, favorites and pins before searching or counting, including the exact expiry boundary', () => {
    const elapsed = document('elapsed', { title: 'Private expiry canary', favorite: true, pinned: true,
      expires_at: '2026-10-23T08:00:00Z' })
    const unavailable = currentDocuments([elapsed, document('missing', { current_revision_id: null })], now)
    expect(unavailable.every(item => item.title === null && item.status === 'expired' && !item.favorite && !item.pinned)).toBe(true)
    expect(visibleDocuments(unavailable, query('q=canary'))).toEqual([])
    expect(visibleDocuments(unavailable, query('status=expired'))).toHaveLength(2)
    expect(elapsed.title).toBe('Private expiry canary')
  })
  it('combines title and status filters within a view and accepts literal search words matching query defaults', () => {
    const items = [document('all'), document('updated'), document('0'), document('other', { is_owner: false })]
    expect(visibleDocuments(items, query('q=all'))[0].id).toBe('all')
    expect(visibleDocuments(items, query('view=shared&status=needs_review&q=other'))).toHaveLength(1)
    expect(visibleDocuments(items, query('view=shared&status=draft'))).toEqual([])
  })
  it('orders pinned documents first, uses last update by default, and does not mutate the authorized list', () => {
    const items = [document('old'), document('new', { updated_at: '2026-10-23T07:30:00Z' }),
      document('pin', { pinned: true, updated_at: '2026-10-21T08:00:00Z' })]
    expect(visibleDocuments(items, query('')).map(item => item.id)).toEqual(['pin', 'new', 'old'])
    expect(visibleDocuments(items, query('sort=title')).map(item => item.id)).toEqual(['pin', 'new', 'old'])
    expect(items.map(item => item.id)).toEqual(['old', 'new', 'pin'])
  })
  it('bounds malformed URL values and keeps every document reachable across pages and after filtering', () => {
    expect(query('view=missing&status=missing&sort=missing&page=-3')).toMatchObject({ view: 'all', status: 'all', sort: 'updated', page: 0 })
    expect(query('page=Infinity').page).toBe(0)
    expect(query('q=' + 'x'.repeat(300)).search).toHaveLength(200)
    const items = Array.from({ length: 61 }, (_, index) => document(String(index)))
    const ordered = visibleDocuments(items, query(''))
    const pages = [0, 1, 2].flatMap(page => {
      const range = pageWindow(ordered.length, page, 25)
      return ordered.slice(range.start, range.end).map(item => item.id)
    })
    expect(new Set(pages).size).toBe(61)
    expect(pageWindow(1, 2, 25).page).toBe(0)
  })
})
