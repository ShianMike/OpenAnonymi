import { afterEach, expect, it, vi } from 'vitest'
import { requestLabel, requestSnapshot, subscribeRequests, trackedRequest } from './requestActivity'

afterEach(() => { vi.unstubAllGlobals(); expect(requestSnapshot()).toEqual([]) })

it('keeps concurrent requests and body consumption active without retaining private inputs', async () => {
  let resolveBody!: (value: string) => void
  const body = new Promise<string>(resolve => { resolveBody = resolve })
  const fetch = vi.fn().mockResolvedValue(new Response('synthetic'))
  vi.stubGlobal('fetch', fetch)
  const listener = vi.fn()
  const unsubscribe = subscribeRequests(listener)
  const a = trackedRequest('/api/v1/documents/private-id/comments?finding=private',
    { method: 'POST', body: 'private source', headers: { 'X-CSRF-Token': 'private token' } }, () => body)
  const b = trackedRequest('/api/v1/documents/another-private-id/exports/txt', { method: 'POST' }, response => response.blob())
  expect(requestSnapshot()).toHaveLength(2)
  expect(JSON.stringify(requestSnapshot())).not.toMatch(/private|token|source|finding=/)
  await b
  expect(requestSnapshot()).toHaveLength(1)
  resolveBody('consumed')
  expect(await a).toBe('consumed')
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(listener).toHaveBeenCalledTimes(4)
  unsubscribe()
})

it('cleans up aborts, network rejection and response parsing errors without retries', async () => {
  const aborted = new DOMException('Aborted', 'AbortError')
  const fetch = vi.fn().mockRejectedValueOnce(aborted).mockResolvedValueOnce(new Response('not JSON'))
  vi.stubGlobal('fetch', fetch)
  await expect(trackedRequest('/api/v1/documents', {}, response => response.json())).rejects.toBe(aborted)
  expect(requestSnapshot()).toEqual([])
  await expect(trackedRequest('/api/v1/documents', {}, response => response.json())).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('names actual operations and ignores readiness checks', async () => {
  expect(requestLabel('/api/v1/documents/id/scan', 'POST')).toBe('Checking for sensitive details')
  expect(requestLabel('/api/v1/documents', 'POST')).toBe('Creating your saved review')
  expect(requestLabel('/api/v1/documents/id/compare', 'GET')).toBe('Comparing saved revisions')
  expect(requestLabel('/api/v1/documents/id/exports/copy', 'POST')).toBe('Preparing reviewed text')
  expect(requestLabel('/api/v1/documents/intake-defaults/workspace', 'GET')).toBe('Loading review defaults')
  expect(requestLabel('/api/v1/documents/id/source', 'PATCH')).toBe('Saving a new source revision')
  const listener = vi.fn()
  const unsubscribe = subscribeRequests(listener)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
  await trackedRequest('/api/v1/health/ready', {}, response => response.json())
  expect(listener).not.toHaveBeenCalled()
  unsubscribe()
})
