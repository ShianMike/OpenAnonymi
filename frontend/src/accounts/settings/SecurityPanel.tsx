import { useEffect, useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'
import {
  changeSecondFactor, confirmEnrollment, getSecondFactor, getSession, startEnrollment,
  type EnrollmentView, type SecondFactorState, type SessionView,
} from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import { AuthenticatorSetup, BackupCodes } from '../AuthenticatorSetup'
import { DevicesPanel } from './DevicesPanel'
import { PasswordPanel } from './AccountPanel'

export function SecurityPanel({ session, onSessionChanged, onSignedOut, onPasswordChanged }: {
  session: SessionView; onSessionChanged: (session: SessionView) => void; onSignedOut: () => void;
  onPasswordChanged: () => void;
}) {
  const [state, setState] = useState<SecondFactorState | null>(null)
  const [enrollment, setEnrollment] = useState<EnrollmentView | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [action, setAction] = useState<'disable' | 'regenerate' | null>(null)
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getSecondFactor(controller.signal).then((value) => { if (!controller.signal.aborted) setState(value) })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Security settings could not be loaded.') })
    return () => controller.abort()
  }, [attempt])
  async function refresh() {
    const [factor, updated] = await Promise.all([getSecondFactor(), getSession()])
    setState(factor); onSessionChanged(updated); setAttempt((value) => value + 1)
  }
  async function start() {
    if (pending) return
    setPending(true); setError(null); setNotice(null)
    try { setEnrollment(await startEnrollment(session.csrf_token)); setCode('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Setup could not be started.') }
    finally { setPending(false) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true); setError(null); setNotice(null)
    try {
      if (action) {
        const result = await changeSecondFactor(password, code, action === 'disable', session.csrf_token)
        setPassword(''); setCode(''); setAction(null)
        if (result) setCodes(result.backup_codes)
        setNotice(result ? 'Your old backup codes no longer work.' : 'Two-step verification disabled. Other sessions were signed out.')
      } else {
        const result = await confirmEnrollment(code, session.csrf_token)
        setCodes(result.backup_codes); setCode(''); setEnrollment(null)
        setNotice('Two-step verification enabled. Other sessions were signed out.')
      }
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The security change could not be completed.') }
    finally { setPending(false) }
  }
  return (
    <div className="security-stack workspace-panel">
      <PasswordPanel session={session} onPasswordChanged={onPasswordChanged} />
      <section className="workspace-panel factor-panel" aria-busy={pending}>
        <PanelHeading icon={ShieldCheck} title="Two-step verification" description="Add a second check with an authenticator app." />
        <div className="factor-content">
        {error && <InlineNotice error>{error}</InlineNotice>}
        {notice && <InlineNotice>{notice}</InlineNotice>}
        {!state && !error && <p role="status">Loading security settings…</p>}
        {!state && error && <button type="button" onClick={() => { setError(null); setAttempt((value) => value + 1) }}>Retry security settings</button>}
        {state && <>
          <p className="security-state"><span className={`settings-status${state.enabled ? ' is-enabled' : ''}`}>{state.enabled ? 'Enabled' : 'Not enabled'}</span>{state.enabled && ` · ${state.backup_codes_remaining} backup codes remaining`}</p>
          {state.locked && <InlineNotice error>Authenticator attempts are locked. Recover your password to unlock attempts, or ask your administrator for a reset.</InlineNotice>}
          {session.second_factor_setup_required && <InlineNotice>A workspace requires two-step verification. Set it up now; your next sign-in will require it.</InlineNotice>}
          {codes ? <BackupCodes codes={codes} onSaved={() => setCodes(null)} /> : <>
            {!state.enabled && !enrollment && <button type="button" onClick={() => void start()} disabled={pending || state.locked}>
              {pending ? 'Preparing setup…' : state.pending_expires_at ? 'Start a new authenticator setup' : 'Set up authenticator'}
            </button>}
            <div className="factor-configuration">
            {enrollment && <AuthenticatorSetup enrollment={enrollment} />}
            {(enrollment || action) && <form className="security-form" onSubmit={submit}>
              <fieldset disabled={pending}>
                {action && <div><label htmlFor="factor-password">Current password</label><GlassInput id="factor-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required maxLength={1024} /></div>}
                <div><label htmlFor="factor-code">{action === 'disable' ? 'Authenticator or backup code' : 'Authenticator code'}</label><GlassInput id="factor-code" autoComplete="one-time-code" inputMode={action === 'disable' ? 'text' : 'numeric'} value={code} onChange={(event) => setCode(event.target.value)} required maxLength={64} aria-describedby={enrollment ? 'factor-code-hint' : undefined} />{enrollment && <p className="field-note" id="factor-code-hint">Enter the 6-digit code from your authenticator app.</p>}</div>
                {action && <p>{action === 'disable' ? 'Disabling removes your authenticator and backup codes and signs out other sessions.' : 'Regenerating replaces all backup codes. Enter a fresh authenticator code.'}</p>}
                <div className="security-actions">
                  <button type="submit">{pending ? 'Verifying…' : action === 'disable' ? 'Confirm disable' : action === 'regenerate' ? 'Regenerate backup codes' : 'Enable two-step verification'}</button>
                  <button type="button" className="quiet-button" onClick={() => { setAction(null); setEnrollment(null); setPassword(''); setCode(''); setError(null) }}>Cancel</button>
                </div>
              </fieldset>
            </form>}
            </div>
            {state.enabled && !action && <div className="security-actions">
              <button type="button" className="quiet-button" disabled={pending || state.locked} onClick={() => { setAction('regenerate'); setError(null); setNotice(null) }}>Replace backup codes</button>
              <button type="button" className="quiet-button" disabled={pending || state.locked || session.memberships.some((item) => item.require_second_factor)}
                title={session.memberships.some((item) => item.require_second_factor) ? 'A workspace requires two-step verification.' : undefined}
                onClick={() => { setAction('disable'); setError(null); setNotice(null) }}>Disable two-step verification</button>
            </div>}
            {state.enabled && session.memberships.some((item) => item.require_second_factor) && <small>A workspace requires two-step verification, so it cannot be disabled.</small>}
          </>}
          <p className="field-note factor-email-note">{state.security_emails_available ? 'Account security changes send an email notice.' : 'Security email notices are unavailable on this site. Security changes still take effect.'}</p>
        </>}
        </div>
      </section>
      <DevicesPanel key={attempt} csrfToken={session.csrf_token} onSignedOut={onSignedOut} />
    </div>
  )
}
