import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Fingerprint, KeyRound, Mail, ShieldCheck } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { AppCredit } from '../ui/AppCredit'
import { useDisplayPreferences } from '../appearance/useDisplayPreferences'
import { AuthCredentials, type CredentialStage } from './AuthCredentials'
import { AuthNotice } from './AuthNotice'
import { RecoveryForm, type RecoveryStep } from './RecoveryForm'
import './auth.css'

type Mode = 'sign-in' | 'sign-up' | 'recovery'

const views = {
  'sign-in': { title: 'Sign in to OpenAnonymi', description: 'Welcome back. Your workspace is waiting.' },
  'sign-up': { title: 'A little more private.', description: 'Start with your email. Make room for thoughtful sharing.' },
  'signup-details': { title: 'Make it yours.', description: 'Choose a password and name your private workspace.' },
  'signup-code': { title: 'Confirm your email.', description: 'Enter the six-digit email code to finish creating your account.' },
  'existing-account': { title: 'Welcome back.', description: 'This email is already registered. Sign in to continue.' },
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
  code: { title: 'Set your password.', description: 'Enter your email code and choose a new password.' },
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
    // Code steps focus their field; replacement views start from the heading.
    if (next === 'credentials' || next === 'backup-codes' || next === 'existing-account') requestAnimationFrame(() => heading.current?.focus())
  }

  const recovering = mode === 'recovery'
  const view = recovering ? views[recoveryStep] : stage === 'credentials' ? views[mode] : views[stage]
  const entry = !recovering && stage === 'credentials'
  // A signed-out visit to a workspace page renders here in place; say why.
  const description = mode === 'sign-in' && entry && !authRoute ? 'Sign in to continue.' : view.description
  const step = recoveryStep === 'code' ? 2 : 1
  const showNotices = mode === 'sign-in' && entry
  const signup = mode === 'sign-up' && ['credentials', 'signup-details', 'signup-code'].includes(stage)
  const steps = recovering ? ['Your email', 'New password'] : ['Email', 'Details', 'Verify']
  const activeStep = recovering ? step - 1 : stage === 'signup-code' ? 2 : stage === 'signup-details' ? 1 : 0
  const Icon = recovering ? KeyRound : stage === 'signup-code' ? Mail : entry || stage === 'signup-details' ? Fingerprint : ShieldCheck

  return (
    <div className="auth-shell" data-mode={mode}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="auth-masthead">
        <Link to="/welcome" className="auth-brand-link" aria-label="OpenAnonymi home">
          <Brand />
        </Link>
        <Link to="/welcome" className="auth-home-link"><ArrowLeft size={16} aria-hidden="true" /> Back to home</Link>
      </header>
      <main id="main-content" className="auth-main" tabIndex={-1}>
        <motion.section className="auth-panel" aria-labelledby="auth-title"
          initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
          {stage !== 'existing-account' && <div className="auth-emblem" aria-hidden="true"><Icon size={28} strokeWidth={1.5} /></div>}
          <motion.h1 key={`${mode}-${recovering ? recoveryStep : stage}`} id="auth-title" ref={heading} tabIndex={-1}
            initial={reducedMotion ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
            {view.title}
            {(recovering || signup) && <span className="sr-only"> Step {activeStep + 1} of {steps.length}.</span>}
          </motion.h1>
          <p className="auth-description">{description}</p>
          {(signup || recovering) && <ol className="auth-progress" aria-label={recovering ? 'Password recovery progress' : 'Account creation progress'}>
            {steps.map((label, index) => <li key={label} aria-current={index === activeStep ? 'step' : undefined} data-complete={index < activeStep || undefined}>
              <span aria-hidden="true">{index + 1}</span>{label}
            </li>)}
          </ol>}
          {showNotices && localNotice && <AuthNotice tone="success">{localNotice}</AuthNotice>}
          {showNotices && !localNotice && notice && <AuthNotice tone="info">{notice}</AuthNotice>}
          <motion.div key={mode} initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={transition}>
          {recovering ? (
            <RecoveryForm
              initialEmail={knownEmail}
              initialStep={recoveryStep}
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
              onSignIn={(email) => {
                setKnownEmail(email)
                switchMode('sign-in')
              }}
              onRecover={(email, hasCode) => {
                setKnownEmail(email)
                switchMode('recovery')
                if (hasCode) setRecoveryStep('code')
              }}
            />
          )}
          </motion.div>
          {signup && (
            <p className="auth-terms">By creating an account, you agree to the <a href="/terms" target="_blank" rel="noopener noreferrer" aria-label="Terms of Service (opens in a new tab)">Terms of Service</a>. Our <a href="/privacy" target="_blank" rel="noopener noreferrer" aria-label="Privacy Notice (opens in a new tab)">Privacy Notice</a> explains how the service handles information.</p>
          )}
          {!recovering && (entry || stage === 'signup-details') && (
            <div className="auth-switch">
              <span>{mode === 'sign-in' ? 'New to OpenAnonymi?' : 'Already have an account?'}</span>
              <button
                type="button"
                className="auth-link"
                onClick={() => switchMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}
              >
                {mode === 'sign-in' ? 'Create an account' : 'Sign in'}
              </button>
            </div>
          )}
          {recovering && <div className="auth-switch"><button type="button" className="auth-link auth-back" onClick={() => switchMode('sign-in')}><ArrowLeft size={15} aria-hidden="true" /> Back to sign in</button></div>}
        </motion.section>
      </main>
      <footer className="auth-footer">
        <AppCredit />
      </footer>
    </div>
  )
}
