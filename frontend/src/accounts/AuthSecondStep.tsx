import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiRequestError, finishForcedEnrollment, finishSecondFactor, startForcedEnrollment,
  type ChallengeView, type EnrollmentView, type SessionView,
} from '../api/client'
import { GlassInput } from '../ui/GlassField'
import { AuthenticatorSetup, BackupCodes } from './AuthenticatorSetup'

export function AuthSecondStep({ challenge, onSignedIn, onRestart, onRecover }: {
  challenge: ChallengeView; onSignedIn: (session: SessionView) => void;
  onRestart: () => void; onRecover: () => void;
}) {
  const [code, setCode] = useState('')
  const [backup, setBackup] = useState(false)
  const [enrollment, setEnrollment] = useState<EnrollmentView | null>(null)
  const [result, setResult] = useState<{ session: SessionView; backup_codes: string[] } | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(() => Date.now() >= Date.parse(challenge.expires_at))
  const enrolling = challenge.status === 'enrollment_required'
  useEffect(() => {
    const timer = window.setInterval(() => setExpired(Date.now() >= Date.parse(challenge.expires_at)), 1000)
    requestAnimationFrame(() => document.getElementById('second-step-code')?.focus())
    return () => window.clearInterval(timer)
  }, [challenge.expires_at])
  function failed(cause: unknown) {
    setError(cause instanceof Error ? cause.message : 'Verification could not be completed.')
    if (cause instanceof ApiRequestError && (cause.status === 401 || cause.code === 'second_factor_locked')) setExpired(true)
  }
  async function start() {
    setPending(true); setError(null)
    try { setEnrollment(await startForcedEnrollment()) }
    catch (cause) { failed(cause) }
    finally { setPending(false) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending || expired) return
    setPending(true); setError(null)
    try {
      if (enrolling) { setResult(await finishForcedEnrollment(code)); setEnrollment(null); setCode('') }
      else { const session = await finishSecondFactor(code); setCode(''); onSignedIn(session) }
    } catch (cause) { failed(cause) }
    finally { setPending(false) }
  }
  if (result) return <BackupCodes codes={result.backup_codes} onSaved={() => onSignedIn(result.session)} />
  return (
    <div className="auth-form" aria-busy={pending}>
      <p>{enrolling ? 'Your account requires authenticator setup before you can continue.' : 'Verify your sign-in with your authenticator or a backup code.'}</p>
      {error && <p role="alert" className="auth-notice">{error}</p>}
      {expired && <p role="status" className="auth-notice">Sign in again to start a new verification step.</p>}
      {enrolling && !enrollment && <button type="button" className="auth-submit" disabled={pending || expired} onClick={() => void start()}>
        {pending ? 'Preparing setup…' : 'Set up authenticator'}
      </button>}
      {enrollment && <AuthenticatorSetup enrollment={enrollment} />}
      {(!enrolling || enrollment) && <form onSubmit={submit}>
        <fieldset className="auth-fields" disabled={pending || expired}>
          <div className="auth-field-row">
            <label htmlFor="second-step-code">{backup ? 'Backup code' : 'Authenticator code'}</label>
            <GlassInput id="second-step-code" value={code} onChange={(event) => setCode(event.target.value)}
              autoComplete="one-time-code" inputMode={backup ? 'text' : 'numeric'} required maxLength={64}
              aria-describedby="second-step-help" />
            <small id="second-step-help" className="field-hint">{backup ? 'Enter one unused backup code. Spaces and hyphens are accepted.' : 'Enter the current six-digit code from your authenticator app.'}</small>
          </div>
          <button type="submit" className="auth-submit">{pending ? 'Verifying…' : enrolling ? 'Enable and continue' : 'Verify sign-in'}</button>
          {!enrolling && <button type="button" className="auth-link" onClick={() => { setBackup(!backup); setCode(''); setError(null) }}>
            {backup ? 'Use authenticator code' : 'Use backup code'}
          </button>}
        </fieldset>
      </form>}
      <div className="second-step-links">
        <button type="button" className="auth-link" disabled={pending} onClick={onRestart}>Back to sign in</button>
        <button type="button" className="auth-link" disabled={pending} onClick={onRecover}>Recover password</button>
      </div>
      <small className="second-step-help">Password recovery keeps two-step verification enabled. If you lost your authenticator and backup codes, ask your administrator for a reset.</small>
    </div>
  )
}
