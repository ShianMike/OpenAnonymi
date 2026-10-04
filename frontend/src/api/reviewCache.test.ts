import { afterEach, expect, it, vi } from 'vitest'
import { ReviewCache, reviewCache, type ReviewStateView } from './reviewCache'
import { getReviewState } from './reviewState'
import { reportEndedScope, setSessionScope } from './sessionEvents'
import { sendJson } from './client'

const tag = '"rs1-' + 'a'.repeat(64) + '"'
const value = (): ReviewStateView => ({ source: { version: { document_id: 'doc' }, text: 'PRIVATE CONTENT',
  expires_at: new Date(Date.now() + 30_000).toISOString() } } as ReviewStateView)
afterEach(() => { reviewCache.clear(); setSessionScope(''); vi.useRealTimers(); vi.unstubAllGlobals() })

it('requires a fresh authorized 304 before returning cloned cached content', async () => {
  setSessionScope('session')
  const initial = value()
  const fetch = vi.fn().mockResolvedValueOnce(Response.json(initial, { headers: { ETag: tag } }))
    .mockResolvedValueOnce(new Response(null, { status: 304, headers: { ETag: tag } }))
  vi.stubGlobal('fetch', fetch)
  const first = await getReviewState('doc', 'session', new AbortController().signal)
  first.source.text = 'LOCAL EDIT'
  const request = getReviewState('doc', 'session', new AbortController().signal)
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[1][1].headers['If-None-Match']).toBe(tag)
  expect(fetch.mock.calls[1][1].cache).toBe('no-store')
  expect((await request).source.text).toBe('PRIVATE CONTENT')
})

it('denied cached access clears retained content and cannot fall back to stale plaintext', async () => {
  setSessionScope('session'); reviewCache.put('session:doc', value(), tag)
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ code: 'document_not_found', message: 'Document not found.' }, { status: 404 })))
  await expect(getReviewState('doc', 'session', new AbortController().signal)).rejects.toMatchObject({ status: 404 })
  expect(reviewCache.get('session:doc')).toBeUndefined()
})

it('late older-session responses and late responses during mutation cannot repopulate the cache', async () => {
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done })))
  setSessionScope('old')
  const request = getReviewState('doc', 'old', new AbortController().signal)
  setSessionScope('new')
  resolve(Response.json(value(), { headers: { ETag: tag } }))
  await expect(request).rejects.toMatchObject({ name: 'AbortError' })
  expect(reviewCache.get('old:doc')).toBeUndefined()
  const next = getReviewState('doc', 'new', new AbortController().signal)
  reviewCache.clear()
  resolve(Response.json(value(), { headers: { ETag: tag } }))
  await expect(next).rejects.toMatchObject({ name: 'AbortError' })
  expect(reviewCache.get('new:doc')).toBeUndefined()
})

it('clears before and after writes, and only the current ended session clears a newer cache', async () => {
  vi.stubGlobal('window', new EventTarget())
  setSessionScope('current'); reviewCache.put('current:doc', value(), tag)
  reportEndedScope('old')
  expect(reviewCache.get('current:doc')).toBeDefined()
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done })))
  const write = sendJson('POST', '/documents/doc/decision', {}, 'current')
  expect(reviewCache.get('current:doc')).toBeUndefined()
  reviewCache.put('current:doc', value(), tag)
  resolve(Response.json({}))
  await write
  expect(reviewCache.get('current:doc')).toBeUndefined()
  reviewCache.put('current:doc', value(), tag); reportEndedScope('current')
  expect(reviewCache.get('current:doc')).toBeUndefined()
})

it('bounds entries and bytes and removes retained content when TTL or document expiry passes', () => {
  vi.useFakeTimers()
  const cache = new ReviewCache(2, 1000, 100)
  cache.put('a', value(), tag); cache.put('b', value(), tag); cache.put('c', value(), tag)
  expect(cache.get('a')).toBeUndefined(); expect(cache.get('c')).toBeDefined()
  vi.advanceTimersByTime(101)
  expect(cache.get('b')).toBeUndefined(); expect(cache.get('c')).toBeUndefined()
  const expired = value(); expired.source.expires_at = new Date(Date.now() - 1).toISOString()
  cache.put('expired', expired, tag); expect(cache.get('expired')).toBeUndefined()
  const huge = value(); huge.source.text = 'x'.repeat(1001)
  cache.put('huge', huge, tag); expect(cache.get('huge')).toBeUndefined()
  cache.clear()
})

it('a successful old-session mutation cannot erase a newer session cache', async () => {
  setSessionScope('old')
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done })))
  const write = sendJson('POST', '/documents/doc/decision', {}, 'old')
  setSessionScope('new'); reviewCache.put('new:doc', value(), tag)
  resolve(Response.json({}))
  await write
  expect(reviewCache.get('new:doc')).toBeDefined()
})
