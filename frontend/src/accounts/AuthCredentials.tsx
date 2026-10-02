import { LoadingMark } from '../loading/LoadingMark'
import { useState, type FormEvent } from 'react'
import { ArrowUpRight, AtSign, LockKeyhole, Layers2 } from 'lucide-react'
import { signIn, signUp, type SessionView } from '../api/client'
import { GlassInput } from '../ui/GlassField'

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
  const creating = mode === 'sign-up'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const session = creating ? await signUp(email, password, workspace) : await signIn(email, password)
      setPassword('')
      onSignedIn(session)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Please try again in a moment.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="auth-form" aria-busy={pending}>
      {error && (
        <p role="alert" className="auth-notice">
          {error}
        </p>
      )}
      <fieldset disabled={pending} className="auth-fields">
        {creating && (
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
        </div>
        <button type="submit" className="auth-submit">
          {pending && <LoadingMark small />}
          {pending
            ? creating
              ? 'Creating your workspace…'
              : 'Signing in…'
            : creating
              ? 'Create account'
              : 'Sign in'}
          {!pending && <ArrowUpRight size={18} aria-hidden="true" />}
        </button>
      </fieldset>
      {pending && (
        <span className="sr-only" role="status">
          {creating ? 'Creating account' : 'Signing in'}
        </span>
      )}
    </form>
  )
}
