import { LoadingMark } from '../loading/LoadingMark'
import { useState, type FormEvent } from 'react'
import { ArrowUpRight, AtSign, LockKeyhole, Layers2 } from 'lucide-react'
import { signIn, signUp, verifySignUp, type ChallengeView, type SessionView } from '../api/client'
import { GlassInput } from '../ui/GlassField'
import { AuthSecondStep } from './AuthSecondStep'

type Props = {
  mode: 'sign-in' | 'sign-up'
  onSignedIn: (session: SessionView) => void
  onRecover: () => void
}

export function AuthCredentials({ mode, onSignedIn, onRecover }: Props) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [code, setCode] = useState('')
  const [requested, setRequested] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [challenge, setChallenge] = useState<ChallengeView | null>(null)
  const creating = mode === 'sign-up'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      if (creating && !requested) {
        const receipt = await signUp(email, password, workspace)
        setMessage(receipt.message)
        setRequested(true)
        requestAnimationFrame(() => document.getElementById('signup-code')?.focus())
        return
      }
      const session = creating ? await verifySignUp(email, code, password) : await signIn(email, password)
      setPassword('')
      if ('status' in session) { setChallenge(session); return }
      onSignedIn(session)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Please try again in a moment.')
    } finally {
      setPending(false)
    }
  }

  if (challenge) return <AuthSecondStep challenge={challenge} onSignedIn={onSignedIn} onRecover={onRecover}
    onRestart={() => { setChallenge(null); setError(null) }} />
  return (
    <form onSubmit={submit} className="auth-form" aria-busy={pending}>
      {error && (
        <p role="alert" className="auth-notice">
          {error}
        </p>
      )}
      {message && <p role="status" className="auth-notice">{message}</p>}
      <fieldset disabled={pending} className="auth-fields">
        {creating && !requested && (
          <div className="auth-field-row">
            <label htmlFor="sign-up-workspace">Workspace name</label>
            <GlassInput
              id="sign-up-workspace"
              icon={Layers2}
              required
              maxLength={120}
              autoComplete="organization"
              placeholder="Your team's space"
              value={workspace}
              onChange={(event) => setWorkspace(event.target.value)}
            />
          </div>
        )}
        {!requested && <div className="auth-field-row">
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
        </div>}
        {requested && <div className="auth-field-row">
          <label htmlFor="signup-code">Email code</label>
          <GlassInput id="signup-code" required autoComplete="one-time-code" maxLength={200}
            value={code} onChange={(event) => setCode(event.target.value)} aria-describedby="signup-code-help" />
          <small id="signup-code-help" className="field-hint">Enter the code sent to {email}. Keep this page open; reloading asks for your password again.</small>
        </div>}
        {!requested && <div className="auth-field-row">
          <div className="auth-label-row">
            <label htmlFor="auth-password">Password</label>
            {!creating && (
              <button type="button" className="auth-link" onClick={onRecover}>
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
            minLength={creating ? 12 : undefined}
            maxLength={1024}
            aria-describedby={creating ? 'password-hint' : undefined}
            placeholder={creating ? 'Create a strong password' : 'Enter your password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {creating && (
            <small id="password-hint" className="field-hint">
              At least 12 characters. A few memorable words work well.
            </small>
          )}
        </div>}
        <button type="submit" className="auth-submit">
          {pending && <LoadingMark small />}
          {pending
            ? creating
              ? requested ? 'Verifying your code…' : 'Sending your code…'
              : 'Signing in…'
            : creating
              ? requested ? 'Verify and create account' : 'Send sign-up code'
              : 'Sign in'}
          {!pending && <ArrowUpRight size={18} aria-hidden="true" />}
        </button>
        {requested && <button type="button" className="auth-link" onClick={() => {
          setRequested(false); setCode(''); setMessage(null); setError(null)
        }}>Edit sign-up details or request a new code</button>}
      </fieldset>
      {!creating && <button type="button" className="auth-link" disabled={pending} onClick={onRecover}>Recover password</button>}
      {pending && (
        <span className="sr-only" role="status">
          {creating ? requested ? 'Verifying your code' : 'Sending your code' : 'Signing in'}
        </span>
      )}
    </form>
  )
}
