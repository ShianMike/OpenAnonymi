import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, LockKeyhole } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { AuthCredentials } from './AuthCredentials'
import { RecoveryForm } from './RecoveryForm'
import './auth.css'

type Mode = 'sign-in' | 'sign-up' | 'recovery'

export function SignInPage({
  onSignedIn,
  notice,
  initialMode = 'sign-in',
}: {
  onSignedIn: (session: SessionView, creatingAccount: boolean) => void
  notice?: string | null
  initialMode?: 'sign-in' | 'sign-up'
}) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [localNotice, setLocalNotice] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  useEffect(() => { heading.current?.focus() }, [])

  function switchMode(next: Mode) {
    setMode(next)
    setLocalNotice(null)
    if (next !== 'recovery' && (pathname === '/sign-in' || pathname === '/sign-up') && pathname !== `/${next}`) {
      void navigate(`/${next}${search}`, { replace: true })
    }
    requestAnimationFrame(() => heading.current?.focus())
  }

  return (
    <div className="auth-shell">
      <header className="auth-masthead">
        <Link to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link>
        <span>YOUR WORDS. YOUR CONTROL.</span>
      </header>
      <main id="main-content" className="auth-stage">
        <div className="auth-intro">
          <span className="auth-kicker">
            <span /> A little more private.
          </span>
          <p>
            Share the story.
            <br />
            <span>Keep identities private.</span>
          </p>
        </div>
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-card-symbol">
            <Brand compact />
          </div>
          <h1 id="auth-title" ref={heading} tabIndex={-1}>
            {mode === 'sign-in'
              ? 'Welcome back.'
              : mode === 'sign-up'
                ? 'Make space for privacy.'
                : 'Let’s get you back in.'}
          </h1>
          <p className="auth-description">
            {mode === 'sign-in'
              ? 'Your next thoughtful review starts here.'
              : mode === 'sign-up'
                ? 'Create an account and a workspace of your own.'
                : 'We’ll send a recovery code to your account email.'}
          </p>
          {(notice || localNotice) && (
            <p role="status" className="auth-notice">
              {localNotice || notice}
            </p>
          )}
          {mode === 'recovery' ? (
            <RecoveryForm
              onComplete={() => {
                switchMode('sign-in')
                setLocalNotice('Password changed. Sign in with your new password.')
              }}
            />
          ) : (
            <AuthCredentials
              key={mode}
              mode={mode}
              onSignedIn={(session) => onSignedIn(session, mode === 'sign-up')}
              onRecover={() => switchMode('recovery')}
            />
          )}
          <div className="auth-switch">
            {mode === 'recovery' ? (
              <button type="button" className="auth-link" onClick={() => switchMode('sign-in')}>
                <ArrowLeft size={14} aria-hidden="true" /> Back to sign in
              </button>
            ) : (
              <>
                <span>{mode === 'sign-in' ? 'New to OpenAnonymi?' : 'Already have an account?'}</span>
                <button
                  type="button"
                  className="auth-link"
                  onClick={() => switchMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}
                >
                  {mode === 'sign-in' ? 'Create an account' : 'Sign in'} <span aria-hidden="true">↗</span>
                </button>
              </>
            )}
          </div>
        </section>
        <p className="auth-footnote">
          <LockKeyhole size={13} aria-hidden="true" /> A private workspace. A considered review.
        </p>
      </main>
      <footer className="auth-footer">
        <span>OPENANONYMI / PRIVACY REVIEW</span>
        <span>Decide what leaves the page.</span>
      </footer>
    </div>
  )
}
