import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowUpRight, KeyRound, ShieldCheck } from 'lucide-react'
import {
  ApiRequestError, finishForcedEnrollment, finishSecondFactor, startForcedEnrollment,
  type ChallengeView, type EnrollmentView, type SessionView,
} from '../api/client'
import { LoadingMark } from '../loading/LoadingMark'
import { GlassInput } from '../ui/GlassField'
import { AuthenticatorSetup, BackupCodes } from './AuthenticatorSetup'
import { AuthNotice } from './AuthNotice'
import { usePendingFocus } from './authFieldHooks'

export function AuthSecondStep({ challenge, onSignedIn, onRestart, onRecover, onBackupCodes }: {
  challenge: ChallengeView; onSignedIn: (session: SessionView) => void;
  onRestart: () => void; onRecover: () => void; onBackupCodes: () => void;
}) {
  const [code, setCode] = useState('')
  const [backup, setBackup] = useState(false)
  const [enrollment, setEnrollment] = useState<EnrollmentView | null>(null)
  const [result, setResult] = useState<{ session: SessionView; backup_codes: string[] } | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(() => Date.now() >= Date.parse(challenge.expires_at))
  const enrolling = challenge.status === 'enrollment_required'
  const focus = usePendingFocus(pending)
  // Focus waits for the render where the code field exists and its fieldset is enabled.
  const focusCode = useRef(false)
  useEffect(() => {
    const element = focusCode.current ? document.getElementById('second-step-code') : null
    if (!element || element.matches(':disabled')) return
    focusCode.current = false
    element.focus()
  })
  useEffect(() => {
    const timer = window.setInterval(() => setExpired(Date.now() >= Date.parse(challenge.expires_at)), 1000)
    requestAnimationFrame(() =>
      (document.getElementById('second-step-code') ?? document.getElementById('second-step-setup'))?.focus(),
    )
    return () => window.clearInterval(timer)
  }, [challenge.expires_at])
  function failed(cause: unknown) {
    setError(cause instanceof Error ? cause.message : 'Verification could not be completed.')
    if (cause instanceof ApiRequestError && (cause.status === 401 || cause.code === 'second_factor_locked')) setExpired(true)
  }
  async function start() {
    focus.remember()
    setPending(true); setError(null)
    try {
      setEnrollment(await startForcedEnrollment())
      focus.forget()
      focusCode.current = true
    }
    catch (cause) { failed(cause) }
    finally { setPending(false) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending || expired) return
    focus.remember()
    setPending(true); setError(null)
    try {
      if (enrolling) {
        const next = await finishForcedEnrollment(code)
        focus.forget()
        setResult(next); setEnrollment(null); setCode('')
        onBackupCodes()
      }
      else { const session = await finishSecondFactor(code); setCode(''); onSignedIn(session) }
    } catch (cause) { failed(cause) }
    finally { setPending(false) }
  }
  if (result) return <BackupCodes codes={result.backup_codes} onSaved={() => onSignedIn(result.session)} />
  return (
    <div className="auth-second-step" aria-busy={pending}>
      {error && <AuthNotice tone="error">{error}</AuthNotice>}
      {expired && <AuthNotice tone="info">Sign in again to start a new verification step.</AuthNotice>}
      {enrolling && !enrollment && (
        <button id="second-step-setup" type="button" className="auth-submit" disabled={pending || expired}
          onClick={() => void start()}>
          <span className="auth-submit-label">
            {pending && <LoadingMark small />}
            {pending ? 'Preparing setup…' : 'Set up authenticator'}
          </span>
          {!pending && <ArrowUpRight size={18} aria-hidden="true" />}
        </button>
      )}
      {enrollment && <AuthenticatorSetup enrollment={enrollment} />}
      {(!enrolling || enrollment) && (
        <form onSubmit={submit} className="auth-form">
          <fieldset className="auth-fields" disabled={pending || expired}>
            <div className="auth-field-row">
              <div className="auth-label-row">
                <label htmlFor="second-step-code">{backup ? 'Backup code' : 'Authenticator code'}</label>
                {!enrolling && (
                  <button type="button" className="auth-link" onClick={() => {
                    setBackup(!backup); setCode(''); setError(null); focusCode.current = true
                  }}>
                    {backup ? 'Use authenticator code' : 'Use backup code'}
                  </button>
                )}
              </div>
              <GlassInput id="second-step-code" className="auth-code-field" icon={backup ? KeyRound : ShieldCheck}
                value={code} onChange={(event) => setCode(event.target.value)}
                autoComplete="one-time-code" inputMode={backup ? 'text' : 'numeric'} spellCheck={false}
                required maxLength={64} aria-describedby="second-step-help" />
              <small id="second-step-help" className="field-hint">
                {backup
                  ? 'Enter one unused backup code. Spaces and hyphens are accepted.'
                  : 'Enter the current six-digit code from your authenticator app.'}
              </small>
            </div>
            <button type="submit" className="auth-submit">
              <span className="auth-submit-label">
                {pending && <LoadingMark small />}
                {pending ? 'Verifying…' : enrolling ? 'Enable and continue' : 'Verify sign-in'}
              </span>
              {!pending && <ArrowUpRight size={18} aria-hidden="true" />}
            </button>
          </fieldset>
        </form>
      )}
      <div className="second-step-links">
        <button type="button" className="auth-link auth-back" disabled={pending} onClick={onRestart}>
          <ArrowLeft size={15} aria-hidden="true" /> Back to sign in
        </button>
        <button type="button" className="auth-link" disabled={pending} onClick={onRecover}>Recover password</button>
      </div>
      <p className="second-step-help">
        Password recovery keeps two-step verification enabled. If you lost your authenticator and backup codes, ask
        your administrator for a reset.
      </p>
    </div>
  )
}
