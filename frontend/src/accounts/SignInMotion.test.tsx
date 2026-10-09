import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { SignInPage } from './SignInPage'

const preferences = vi.hoisted(() => ({ reducedMotion: false }))
vi.mock('../appearance/useDisplayPreferences', () => ({ useDisplayPreferences: () => preferences }))

it.each([false, true])('honors reduced motion (%s) while preserving account form semantics', (reducedMotion) => {
  preferences.reducedMotion = reducedMotion
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={['/sign-up']}><SignInPage initialMode="sign-up" onSignedIn={() => {}} /></MemoryRouter>)
  const heading = html.match(/<h1[^>]*>/)?.[0]
  expect(heading).toContain(`opacity:${reducedMotion ? 1 : 0}`)
  expect(html.match(/<input id="auth-password"[^>]*>/)?.[0]).toMatch(/autocomplete="new-password"/i)
  expect(html).toContain('By creating an account, you agree to the')
  expect(html).toContain('href="/privacy" target="_blank" rel="noopener noreferrer"')
})
