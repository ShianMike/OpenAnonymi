import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowUpRight } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { AppCredit } from '../ui/AppCredit'
import { BorderBeam } from '../ui/BorderBeam'
import { useLoadingMotion } from '../loading/useLoadingMotion'
import { useDisplayPreferences } from '../appearance/useDisplayPreferences'
import { AuthCredentials, type CredentialStage } from './AuthCredentials'
import { AuthNotice } from './AuthNotice'
import { AuthStory } from './AuthStory'
import { RecoveryForm, type RecoveryStep } from './RecoveryForm'
import './auth.css'

type Mode = 'sign-in' | 'sign-up' | 'recovery'

const views = {
  'sign-in': { title: 'Welcome back.', description: 'Your next thoughtful review starts here.' },
  'sign-up': { title: 'Make space for privacy.', description: 'Create an account and a workspace of your own.' },
  'signup-code': { title: 'Confirm your email.', description: 'Enter the code from the email to finish creating your account.' },
  'second-factor': {
    title: 'Verify it’s you.',
    description: 'Enter the six-digit code from your authenticator app, or use a backup code.',
  },
  enrollment: {
    title: 'Set up two-step verification.',
    description: 'Your account needs an authenticator app before you can continue.',
  },
  'backup-codes': { title: 'Two-step verification is on.', description: 'Save your backup codes before your workspace opens.' },
  request: { title: 'Let’s get you back in.', description: 'Enter your account email and we’ll send you a recovery code.' },
  code: { title: 'Check your inbox.', description: 'Paste the code from the email, then choose a new password.' },
}

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
  const [stage, setStage] = useState<CredentialStage>('credentials')
  const [recoveryStep, setRecoveryStep] = useState<RecoveryStep>('request')
  const [localNotice, setLocalNotice] = useState<string | null>(null)
  const [knownEmail, setKnownEmail] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const panelMotion = useLoadingMotion<HTMLElement>()
  const { reducedMotion } = useDisplayPreferences()
  const transition = { duration: reducedMotion ? 0 : .18, ease: 'easeOut' as const }
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const authRoute = pathname === '/sign-in' || pathname === '/sign-up'
  useEffect(() => { heading.current?.focus() }, [])

  function switchMode(next: Mode) {
    setMode(next)
    setStage('credentials')
    setRecoveryStep('request')
    setLocalNotice(null)
    if (next !== 'recovery' && authRoute && pathname !== `/${next}`) {
      void navigate(`/${next}${search}`, { replace: true })
    }
    requestAnimationFrame(() => heading.current?.focus())
  }

  function changeStage(next: CredentialStage) {
    setStage(next)
    // Code steps focus their field; these two replace the form, so start from the heading.
    if (next === 'credentials' || next === 'backup-codes') requestAnimationFrame(() => heading.current?.focus())
  }

  const recovering = mode === 'recovery'
  const view = recovering ? views[recoveryStep] : stage === 'credentials' ? views[mode] : views[stage]
  const entry = !recovering && stage === 'credentials'
  // A signed-out visit to a workspace page renders here in place; say why.
  const description = mode === 'sign-in' && entry && !authRoute ? 'Sign in to continue.' : view.description
  const step = recoveryStep === 'code' ? 2 : 1
  const showNotices = mode === 'sign-in' && entry

  return (
    <div className="auth-shell" data-mode={mode}>
      <header className="auth-masthead">
        <Link to="/welcome" className="auth-brand-link" aria-label="OpenAnonymi home">
          <Brand />
        </Link>
      </header>
      <main id="main-content" className="auth-main">
        <motion.section ref={panelMotion} className="auth-panel auth-card" aria-labelledby="auth-title"
          initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
          <BorderBeam />
          {recovering && (
            <div className="auth-recovery-nav">
              <button type="button" className="auth-link auth-back" onClick={() => switchMode('sign-in')}>
                <ArrowLeft size={15} aria-hidden="true" /> Back to sign in
              </button>
              <p className="auth-step" aria-hidden="true">
                <span className="auth-step-track">
                  <i data-done="true" />
                  <i data-done={step === 2 ? 'true' : undefined} />
                </span>
                Step {step} of 2
              </p>
            </div>
          )}
          <motion.h1 key={`${mode}-${recovering ? recoveryStep : stage}`} id="auth-title" ref={heading} tabIndex={-1}
            initial={reducedMotion ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
            {view.title}
            {recovering && <span className="sr-only"> Step {step} of 2.</span>}
          </motion.h1>
          <p className="auth-description">{description}</p>
          {showNotices && localNotice && <AuthNotice tone="success">{localNotice}</AuthNotice>}
          {showNotices && !localNotice && notice && <AuthNotice tone="info">{notice}</AuthNotice>}
          <motion.div key={mode} initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
          {recovering ? (
            <RecoveryForm
              initialEmail={knownEmail}
              onStepChange={setRecoveryStep}
              onComplete={(email) => {
                setKnownEmail(email)
                switchMode('sign-in')
                setLocalNotice('Password changed. Sign in with your new password. Any other sessions were signed out.')
              }}
            />
          ) : (
            <AuthCredentials
              key={mode}
              mode={mode}
              initialEmail={knownEmail}
              onStageChange={changeStage}
              onSignedIn={(session) => onSignedIn(session, mode === 'sign-up')}
              onRecover={(email) => {
                setKnownEmail(email)
                switchMode('recovery')
              }}
            />
          )}
          </motion.div>
          {!recovering && (stage === 'credentials' || stage === 'signup-code') && (
            <div className="auth-switch">
              <span>{mode === 'sign-in' ? 'New to OpenAnonymi?' : 'Already have an account?'}</span>
              <button
                type="button"
                className="auth-link"
                onClick={() => switchMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}
              >
                {mode === 'sign-in' ? 'Create an account' : 'Sign in'} <ArrowUpRight size={14} aria-hidden="true" />
              </button>
            </div>
          )}
        </motion.section>
      </main>
      <AuthStory />
      <footer className="auth-footer">
        <AppCredit />
      </footer>
    </div>
  )
}
