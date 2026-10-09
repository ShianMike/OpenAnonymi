import { afterEach, expect, it, vi } from 'vitest'
import { get, requireSuccess } from './client'
import { trackedRequest } from './requestActivity'
import { matchesSessionScope, SESSION_ENDED_EVENT, setSessionScope } from './sessionEvents'

afterEach(() => { vi.unstubAllGlobals(); setSessionScope('') })

it('does not sign out a newer session when an older protected request finishes late', async () => {
  const browser = new EventTarget()
  vi.stubGlobal('window', browser)
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((done) => { resolve = done })))
  let currentSession = 'old-session-scope'
  setSessionScope(currentSession)
  browser.addEventListener(SESSION_ENDED_EVENT, (event) => { if (matchesSessionScope(event, currentSession)) currentSession = '' })
  const request = get('/documents')
  currentSession = 'new-session-scope'
  setSessionScope(currentSession)
  resolve(Response.json({ code: 'sign_in_required', message: 'Sign in to continue.' }, { status: 401 }))
  await expect(request).rejects.toMatchObject({ status: 401 })
  expect(currentSession).toBe('new-session-scope')
})

it('reports actual protected session expiry with the request session, including POST requests', async () => {
  const browser = new EventTarget(), events: Event[] = []
  vi.stubGlobal('window', browser)
  browser.addEventListener(SESSION_ENDED_EVENT, (event) => events.push(event))
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ code: 'sign_in_required', message: 'Sign in to continue.' }, { status: 401 })))
  setSessionScope('old-scope')
  await expect(trackedRequest('/search/documents', { method: 'POST', headers: { 'X-CSRF-Token': 'current-scope' } }, requireSuccess)).rejects.toMatchObject({ status: 401 })
  expect(events).toHaveLength(1)
  expect(matchesSessionScope(events[0], 'current-scope')).toBe(true)
  expect(matchesSessionScope(events[0], 'old-scope')).toBe(false)
})

it('keeps wrong passwords and inaccessible documents separate from session expiry', async () => {
  const browser = new EventTarget(), listener = vi.fn()
  vi.stubGlobal('window', browser)
  browser.addEventListener(SESSION_ENDED_EVENT, listener)
  setSessionScope('current-scope')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ code: 'credentials_invalid', message: 'Invalid credentials.' }, { status: 401 }))
    .mockResolvedValueOnce(Response.json({ code: 'document_not_found', message: 'Document not found.' }, { status: 404 })))
  await expect(get('/auth/sign-in')).rejects.toMatchObject({ status: 401 })
  await expect(get('/documents/missing')).rejects.toMatchObject({ status: 404 })
  expect(listener).not.toHaveBeenCalled()
})
