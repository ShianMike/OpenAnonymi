import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { SignInPage } from './SignInPage'
import { RecoveryForm } from './RecoveryForm'
import { AuthSecondStep } from './AuthSecondStep'
import { ExistingAccountNotice } from './AuthNotice'

const preferences = vi.hoisted(() => ({ reducedMotion: false }))
vi.mock('../appearance/useDisplayPreferences', () => ({ useDisplayPreferences: () => preferences }))

it('gives an existing account a clear sign-in path, recovery and an email correction', () => {
  const html = renderToStaticMarkup(<ExistingAccountNotice email="member@example.test" onSignIn={() => {}} onRecover={() => {}} onChangeEmail={() => {}} />)
  expect(html).toContain('Already registered account')
  expect(html.match(/member@example.test/g)).toHaveLength(1)
  expect(html).toContain('Continue to sign in')
  expect(html).toContain('Reset password')
  expect(html).toContain('aria-label="Use a different email"')
  expect(html).not.toContain('role="alert"')
  expect(html).not.toContain('<form')
})

it.each([false, true])('honors reduced motion (%s) while preserving account form semantics', (reducedMotion) => {
  preferences.reducedMotion = reducedMotion
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={['/sign-up']}><SignInPage initialMode="sign-up" onSignedIn={() => {}} /></MemoryRouter>)
  const heading = html.match(/<h1[^>]*>/)?.[0]
  expect(heading).toContain(`opacity:${reducedMotion ? 1 : 0}`)
  expect(html.match(/<input id="auth-email"[^>]*>/)?.[0]).toMatch(/autocomplete="username"/i)
  expect(html).toContain('Continue with email')
  expect(html).not.toContain('id="auth-password"')
  expect(html).not.toContain('id="sign-up-workspace"')
  expect(html).toContain('By creating an account, you agree to the')
  expect(html).toContain('href="/privacy" target="_blank" rel="noopener noreferrer"')
})

it('keeps sign-in directly accessible with password-manager fields and recovery', () => {
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={['/sign-in']}><SignInPage onSignedIn={() => {}} /></MemoryRouter>)
  expect(html.match(/<input id="auth-password"[^>]*>/)?.[0]).toMatch(/autocomplete="current-password"/i)
  expect(html).toContain('Forgot password?')
  expect(html).toContain('Use your invitation code')
  expect(html).toContain('Skip to content')
})

it('lets an invitation holder enter an existing code without requesting another', () => {
  const html = renderToStaticMarkup(<RecoveryForm initialStep="code" onStepChange={() => {}} onComplete={() => {}} />)
  expect(html.match(/<input id="recovery-email"[^>]*>/)?.[0]).not.toContain('readOnly')
  expect(html.match(/<input id="recovery-code"[^>]*>/)?.[0]).toMatch(/autocomplete="one-time-code"/i)
  expect(html.match(/<input id="recovery-password"[^>]*>/)?.[0]).toMatch(/minlength="12"/i)
  expect(html).toContain('Need a code?')
})

it.each([false, true])('keeps second-factor challenges accessible and respects expiration (%s)', (expired) => {
  const html = renderToStaticMarkup(<AuthSecondStep
    challenge={{ status: 'second_factor_required', expires_at: new Date(Date.now() + (expired ? -60_000 : 60_000)).toISOString() }}
    onSignedIn={() => {}} onRestart={() => {}} onRecover={() => {}} onBackupCodes={() => {}}
  />)
  expect(html).toContain('Use backup code')
  expect(html.match(/<input id="second-step-code"[^>]*>/)?.[0]).toMatch(/autocomplete="one-time-code"/i)
  expect(html.match(/<fieldset[^>]*>/)?.[0].includes('disabled')).toBe(expired)
})
