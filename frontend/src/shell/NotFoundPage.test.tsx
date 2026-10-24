import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { NotFoundPage } from './NotFoundPage'

const state = vi.hoisted(() => ({ preferred: null as string | null }))
vi.mock('../resume/reviewWorkspace', () => ({ useReviewWorkspace: () => state.preferred }))

const session = { user_id: 'synthetic', memberships: [
  { workspace_id: 'first', workspace_name: 'First workspace', role: 'member' },
  { workspace_id: 'second', workspace_name: 'Second workspace', role: 'administrator' },
] } as SessionView
const render = (route: string, currentSession?: SessionView) => renderToStaticMarkup(
  <MemoryRouter initialEntries={[route]}><NotFoundPage session={currentSession} /></MemoryRouter>,
)

it('offers local recovery destinations for a signed-out visitor without requiring browser history', () => {
  const html = render('/unknown?workspace=untrusted&next=https://example.test')
  expect(html).toContain('<h1 id="not-found-title">Page not found</h1>')
  expect(html).toContain('<main id="main-content">')
  expect(html).toContain('href="/sign-in"')
  expect(html).toContain('href="/welcome"')
  expect(html).not.toContain('href="/documents')
  expect(html).not.toContain('https://example.test')
})

it('preserves only an authorized workspace in both signed-in recovery links', () => {
  const selected = render('/unknown?workspace=second', session)
  expect(selected).toContain('href="/documents?workspace=second"')
  expect(selected).toContain('href="/?workspace=second"')
  expect(selected).not.toContain('<main')
  expect(selected).not.toContain('href="/sign-in"')
  state.preferred = 'second'
  try {
    expect(render('/unknown', session)).toContain('href="/documents?workspace=second"')
    const invalid = render('/unknown?workspace=not-a-member', session)
    expect(invalid).toContain('href="/documents?workspace=second"')
    expect(invalid).not.toContain('not-a-member')
    state.preferred = 'removed-workspace'
    expect(render('/unknown', session)).toContain('href="/documents?workspace=first"')
    expect(render('/unknown', { ...session, memberships: [] })).toContain('href="/documents"')
  } finally { state.preferred = null }
})
