import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { SessionView } from '../../api/client'
import { EmailVerification } from './EmailVerification'

it('keeps email ownership states distinct and offers verification only when delivery is available', () => {
  const session = { email: 'member@example.test', email_verified: false, email_verification_available: true } as SessionView
  const render = (current: SessionView) => renderToStaticMarkup(<EmailVerification session={current} onVerified={() => {}} />)
  const available = render(session)
  expect(available.match(/member@example.test/g)).toHaveLength(1)
  expect(available).toContain('Not verified')
  expect(available).toContain('Verify your email')
  expect(available).toContain('Enter a code')
  expect(available).not.toContain('<form')
  const unavailable = render({ ...session, email_verification_available: false })
  expect(unavailable).toContain('Email verification is unavailable')
  expect(unavailable).not.toContain('<button')
  const verified = render({ ...session, email_verified: true })
  expect(verified).toContain('Your email address is verified.')
  expect(verified).toContain('role="status"')
  expect(verified).not.toContain('<button')
  expect(verified).not.toContain('Not verified')
})
