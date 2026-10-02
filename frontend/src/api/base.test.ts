import { afterEach, expect, it, vi } from 'vitest'
import { API_BASE, apiUrl, DEFAULT_API_BASE, resolveApiBase } from './base'
import { getMetadata, signOut } from './client'

afterEach(() => { vi.unstubAllGlobals() })

it('uses the same-origin default and normalizes a configured base', () => {
  expect(resolveApiBase(undefined)).toBe(DEFAULT_API_BASE)
  expect(resolveApiBase('  ')).toBe(DEFAULT_API_BASE)
  expect(resolveApiBase('https://api.example.invalid/api/v1')).toBe('https://api.example.invalid/api/v1')
  expect(resolveApiBase('https://api.example.invalid/api/v1//')).toBe('https://api.example.invalid/api/v1')
  expect(API_BASE).toBe(DEFAULT_API_BASE)
  expect(apiUrl('/auth/session')).toBe('/api/v1/auth/session')
})

it('sends credentials with every API request so a cross-site session cookie is used', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('{"name":"OpenAnonymi"}'))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetch)
  await getMetadata()
  await signOut('synthetic-csrf')
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/meta', '/api/v1/auth/sign-out'])
  for (const [, init] of fetch.mock.calls) {
    expect(init).toMatchObject({ credentials: 'include', cache: 'no-store' })
  }
  expect(fetch.mock.calls[1][1].headers).toEqual({ 'X-CSRF-Token': 'synthetic-csrf' })
})
