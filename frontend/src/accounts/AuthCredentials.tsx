import { LoadingMark } from '../loading/LoadingMark'
import { useState, type FormEvent } from 'react'
import { ArrowRight, ArrowUpRight, AtSign, ChevronDown, CircleHelp, KeyRound, LockKeyhole, Layers2, Mail } from 'lucide-react'
import { signIn, signUp, verifySignUp, type ChallengeView, type SessionView } from '../api/client'
import { GlassInput } from '../ui/GlassField'
import { AuthNotice, CapsLockNote, PasswordRequirement } from './AuthNotice'
import { AuthSecondStep } from './AuthSecondStep'
import { PASSWORD_MIN_LENGTH, useCapsLock, usePendingFocus } from './authFieldHooks'

/** Where the visitor is inside sign in or sign up; the page heading follows it. */
export type CredentialStage = 'credentials' | 'signup-code' | 'second-factor' | 'enrollment' | 'backup-codes'

type Props = {
  mode: 'sign-in' | 'sign-up'
  initialEmail?: string
  onSignedIn: (session: SessionView) => void
  onRecover: (email: string) => void
  onStageChange: (stage: CredentialStage) => void
}

export function AuthCredentials({ mode, initialEmail = '', onSignedIn, onRecover, onStageChange }: Props) {
  const [pending, setPending] = useState<'request' | 'complete' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState(initialEmail)
  const [password, setPassword] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [code, setCode] = useState('')
  const [requested, setRequested] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [challenge, setChallenge] = useState<ChallengeView | null>(null)
  const creating = mode === 'sign-up'
  const busy = pending !== null
  const focus = usePendingFocus(busy)
  const { capsLock, capsLockProps } = useCapsLock()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(creating && !requested ? 'request' : 'complete')
  }

  async function run(action: 'request' | 'complete') {
    if (pending) return
    focus.remember()
    setPending(action)
    setError(null)
    try {
      if (action === 'request') {
        const receipt = await signUp(email, password, workspace)
        setMessage(requested ? `Requested again. ${receipt.message}` : receipt.message)
        setCode('')
        setRequested(true)
        focus.forget()
        onStageChange('signup-code')
        requestAnimationFrame(() => document.getElementById('signup-code')?.focus())
        return
      }
      // Emailed codes never contain whitespace; pasted copies often do.
      const session = creating ? await verifySignUp(email, code.replace(/\s/g, ''), password) : await signIn(email, password)
      setPassword('')
      if ('status' in session) {
        focus.forget()
        setChallenge(session)
        onStageChange(session.status === 'enrollment_required' ? 'enrollment' : 'second-factor')
        return
      }
      onSignedIn(session)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Please try again in a moment.')
    } finally {
      setPending(null)
    }
  }

  function editDetails() {
    setRequested(false)
    setCode('')
    setMessage(null)
    setError(null)
    onStageChange('credentials')
    requestAnimationFrame(() => document.getElementById('auth-email')?.focus())
  }

  if (challenge) {
    return (
      <AuthSecondStep
        challenge={challenge}
        onSignedIn={onSignedIn}
        onRecover={() => onRecover(email)}
        onBackupCodes={() => onStageChange('backup-codes')}
        onRestart={() => {
          setChallenge(null)
          setError(null)
          onStageChange('credentials')
        }}
      />
    )
  }

  const passwordNotes = [creating && 'password-hint', capsLock && 'auth-password-caps'].filter(Boolean).join(' ')

  return (
    <form onSubmit={submit} className="auth-form" aria-busy={busy}>
      {error && <AuthNotice tone="error">{error}</AuthNotice>}
      {message && <p className="sr-only" role="status">{message}</p>}
      <fieldset disabled={busy} className="auth-fields">
        {!requested && (
          <>
            <div className="auth-field-row">
              <label htmlFor="auth-email">Email address</label>
              <GlassInput
                id="auth-email"
                icon={AtSign}
                type="email"
                autoComplete="username"
                required
                maxLength={320}
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div className="auth-field-row">
              <div className="auth-label-row">
                <label htmlFor="auth-password">Password</label>
                {!creating && (
                  <button type="button" className="auth-link" onClick={() => onRecover(email)}>
                    Forgot password?
                  </button>
                )}
              </div>
              <GlassInput
                id="auth-password"
                icon={LockKeyhole}
                type="password"
                required
                autoComplete={creating ? 'new-password' : 'current-password'}
                minLength={creating ? PASSWORD_MIN_LENGTH : undefined}
                maxLength={1024}
                aria-describedby={passwordNotes || undefined}
                placeholder={creating ? 'Create a strong password' : 'Enter your password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                {...capsLockProps}
              />
              {creating && (
                <PasswordRequirement id="password-hint" value={password} tip="A few memorable words work well." />
              )}
              <CapsLockNote id="auth-password-caps" on={capsLock} />
            </div>
            {creating && (
              <div className="auth-field-row">
                <label htmlFor="sign-up-workspace">Workspace name</label>
                <GlassInput
                  id="sign-up-workspace"
                  icon={Layers2}
                  required
                  maxLength={120}
                  autoComplete="organization"
                  aria-describedby="workspace-hint"
                  placeholder="Your team's space"
                  value={workspace}
                  onChange={(event) => setWorkspace(event.target.value)}
                />
                <small id="workspace-hint" className="field-hint">
                  Your own private space for reviews. You’ll be its administrator.
                </small>
              </div>
            )}
          </>
        )}
        {requested && (
          <div className="auth-code-destination">
            <Mail size={20} aria-hidden="true" />
            <div><span>Your sign-up email</span><strong>{email}</strong></div>
            <button type="button" className="auth-link" onClick={editDetails}>Change</button>
          </div>
        )}
        {requested && (
          <div className="auth-field-row">
            <label htmlFor="signup-code">Email code</label>
            <GlassInput
              id="signup-code"
              className="auth-code-field"
              icon={KeyRound}
              required
              autoComplete="one-time-code"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              maxLength={200}
              placeholder="Paste the code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              aria-describedby="signup-code-help"
            />
            <small id="signup-code-help" className="field-hint">
              Use the latest code. It expires after 15 minutes.
            </small>
          </div>
        )}
        <button type="submit" className="auth-submit" disabled={requested && !code.trim()}>
          <span className="auth-submit-label">
            {pending && (!requested || pending === 'complete') && <LoadingMark small />}
            {pending && (!requested || pending === 'complete')
              ? creating
                ? requested
                  ? 'Verifying your code…'
                  : 'Sending your code…'
                : 'Signing in…'
              : creating
                ? requested
                  ? 'Verify and create account'
                  : 'Send sign-up code'
                : 'Sign in'}
          </span>
          {!pending && (requested ? <ArrowRight size={18} aria-hidden="true" /> : <ArrowUpRight size={18} aria-hidden="true" />)}
        </button>
        {requested && (
          <p className="auth-resend">
            <span>No email yet?</span>
            <button type="button" className="auth-link" onClick={() => void run('request')}>
              {pending === 'request' ? 'Requesting a code…' : 'Send a new code'}
            </button>
          </p>
        )}
        {requested && (
          <details className="auth-code-help">
            <summary><CircleHelp size={16} aria-hidden="true" /><span>Can't find your code?</span><ChevronDown size={15} aria-hidden="true" /></summary>
            <div className="auth-code-help-body">
              <p>Check your spam folder for the latest OpenAnonymi email. Keep this page open while you check.</p>
              <small>Sign-up codes are sent only to addresses eligible for a new account.</small>
              <div className="auth-code-recovery">
                <span><strong>Already registered?</strong><small>Recover access to your existing account.</small></span>
                <button type="button" className="auth-link" disabled={busy} onClick={() => onRecover(email)}>Recover account <ArrowRight size={14} aria-hidden="true" /></button>
              </div>
            </div>
          </details>
        )}
      </fieldset>
      {!creating && (
        <p className="auth-alt-action">
          <span>Invited to a workspace?</span>
          <button type="button" className="auth-link" disabled={busy} onClick={() => onRecover(email)}>
            Recover password
          </button>
        </p>
      )}
      {pending && (
        <span className="sr-only" role="status">
          {pending === 'request' ? 'Requesting your code' : creating ? 'Verifying your code' : 'Signing in'}
        </span>
      )}
    </form>
  )
}
