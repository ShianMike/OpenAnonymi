import { expect, it } from 'vitest'
import type { DocumentIndexView } from '../../api/client'
import { recentAvailableReviews, reviewsInProgress } from './overviewPresentation'

it('counts unfinished work without treating expired or completed reviews as resumable', () => {
  expect(reviewsInProgress({ draft: 2, scanning: 1, needs_review: 3, failed: 1, ready: 8, exported: 9, expired: 20, deleted: 4 })).toBe(7)
  expect(reviewsInProgress({ expired: 5 })).toBe(0)
  expect(reviewsInProgress({})).toBe(0)
})

it('shows the five most recently updated available reviews without changing the source list', () => {
  const now = Date.parse('2026-10-22T00:00:00Z')
  const items = Array.from({ length: 7 }, (_, index) => ({
    id: String(index), status: 'needs_review', is_owner: index % 2 === 0,
    updated_at: new Date(now - index * 1000).toISOString(), expires_at: new Date(now + 60_000).toISOString(),
  } as DocumentIndexView)).reverse()
  const original = items.map(item => item.id)
  expect(recentAvailableReviews(items, now).map(item => item.id)).toEqual(['0', '1', '2', '3', '4'])
  expect(items.map(item => item.id)).toEqual(original)
})

it('hides a review as soon as its retention expires, even before the server status changes', () => {
  const now = Date.parse('2026-10-22T00:00:00Z')
  const item = { id: 'review', status: 'ready', updated_at: new Date(now).toISOString(), expires_at: new Date(now).toISOString() } as DocumentIndexView
  expect(recentAvailableReviews([item], now)).toEqual([])
  expect(recentAvailableReviews([{ ...item, expires_at: new Date(now + 1).toISOString() }], now)).toHaveLength(1)
  expect(recentAvailableReviews([{ ...item, status: 'deleted', expires_at: new Date(now + 1).toISOString() }], now)).toEqual([])
})
