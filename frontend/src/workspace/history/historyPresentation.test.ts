import { expect, it } from 'vitest'
import type { DocumentHistoryView } from '../../api/client'
import { historyAvailable, historyDays } from './historyPresentation'

const history = { status: 'draft', expires_at: '2026-10-23T12:00:00Z' } as DocumentHistoryView

it('stops offering source versions at the retention boundary and for unavailable reviews', () => {
  const expiry = Date.parse(history.expires_at)
  expect(historyAvailable(history, expiry - 1)).toBe(true)
  expect(historyAvailable(history, expiry)).toBe(false)
  expect(historyAvailable({ ...history, status: 'deleted' }, expiry - 1)).toBe(false)
  expect(historyAvailable({ ...history, status: 'expired' }, expiry - 1)).toBe(false)
  expect(historyAvailable({ ...history, expires_at: 'invalid' }, expiry - 1)).toBe(false)
})

it('groups activity by local calendar day while keeping the server order', () => {
  const events = [
    { event_code: 'source_revised', outcome: 'completed', occurred_at: '2026-10-23T12:00:00Z' },
    { event_code: 'scan_failed', outcome: 'failed', occurred_at: '2026-10-23T11:00:00Z' },
    { event_code: 'document_created', outcome: 'completed', occurred_at: '2026-10-22T12:00:00Z' },
  ]
  const days = historyDays(events, '2026-10-23T13:00:00Z')
  expect(days.map(day => day.label)).toEqual(['Today', 'Yesterday'])
  expect(days.map(day => day.events)).toEqual([events.slice(0, 2), events.slice(2)])
  expect(historyDays([], '2026-10-23T13:00:00Z')).toEqual([])
})
