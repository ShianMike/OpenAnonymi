import { useEffect, useRef, useState, type FormEvent } from 'react'
import { changePassword, changeSecondFactor, confirmEnrollment, getSecondFactor, getSession, startEnrollment,
  type EnrollmentView, type SecondFactorState, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { LoadingState } from '../../loading/LoadingState'
import { AuthenticatorSetup, BackupCodes } from '../AuthenticatorSetup'
import { SettingsConfirmation } from './SettingsConfirmation'

export function SecurityPanel({ session, onSessionChanged, onPasswordChanged }: {
  session: SessionView; onSessionChanged: (session: SessionView) => void; onPasswordChanged: () => void
}) {
  const [state, setState] = useState<SecondFactorState | null>(null)
  const [enrollment, setEnrollment] = useState<EnrollmentView | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [action, setAction] = useState<'disable' | 'regenerate' | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [pending, setPending] = useState<'password' | 'factor' | null>(null)
  const [review, setReview] = useState<'password' | 'disable' | 'regenerate' | null>(null)
  const [passwordError, setPasswordError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const saveButton = useRef<HTMLButtonElement | null>(null)
  const policyRequired = session.memberships.some(item => item.require_second_factor)
  useEffect(() => {
    const controller = new AbortController()
    getSecondFactor(controller.signal).then(value => { if (!controller.signal.aborted) setState(value) })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Security settings could not be loaded.') })
    return () => controller.abort()
  }, [attempt])
  async function refresh() {
    const [factor, updated] = await Promise.all([getSecondFactor(), getSession()])
    setState(factor); onSessionChanged(updated)
  }
  async function start() {
    if (pending) return
    setPending('factor'); setError(''); setNotice('')
    try { setEnrollment(await startEnrollment(session.csrf_token)); setCode('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Setup could not be started.') }
    finally { setPending(null) }
  }
  async function saveFactor() {
    if (pending || !code.trim() || (action && !password)) return
    setPending('factor'); setError(''); setNotice('')
    try {
      if (action) {
        const result = await changeSecondFactor(password, code, action === 'disable', session.csrf_token)
        setPassword(''); setCode(''); setAction(null)
        if (result) setCodes(result.backup_codes)
        setNotice(result ? 'Backup codes replaced. Your old codes no longer work.' : 'Two-step verification disabled. Other sessions were signed out.')
      } else {
        const result = await confirmEnrollment(code, session.csrf_token)
        setCodes(result.backup_codes); setCode(''); setEnrollment(null)
        setNotice('Two-step verification enabled. Other sessions were signed out.')
      }
      setReview(null)
      try { await refresh() } catch { setError('The security change was saved, but its status could not be refreshed. Reload security status before making another change.'); setState(null) }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The security change could not be completed.') }
    finally { setPending(null) }
  }
  async function savePassword() {
    if (pending || !currentPassword || newPassword.length < 12) return
    setPending('password'); setPasswordError('')
    try { await changePassword(currentPassword, newPassword, session.csrf_token); setCurrentPassword(''); setNewPassword(''); onPasswordChanged() }
    catch (cause) { setPasswordError(cause instanceof Error ? cause.message : 'Password could not be changed.') }
    finally { setPending(null) }
  }
  function reviewPassword(event: FormEvent) { event.preventDefault(); setPasswordError(''); setReview('password') }
  return <>
    <section className="settings-section" aria-labelledby="settings-password-title"><header className="settings-section-heading"><h3 id="settings-password-title">Password</h3><p>Changing your password signs you out on every device, including this one.</p></header>
      <form className="settings-password-form" onSubmit={reviewPassword}><fieldset disabled={!!pending}>
        <div className="settings-field"><label htmlFor="current-password">Current password</label><GlassInput id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} required maxLength={1024} /></div>
        <div className="settings-field"><label htmlFor="changed-password">New password</label><GlassInput id="changed-password" type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required minLength={12} maxLength={1024} aria-describedby="new-password-hint" /><p id="new-password-hint">Use at least 12 characters.</p></div>
      </fieldset>{passwordError && review !== 'password' && <InlineNotice error title="Password change needs attention">{passwordError}</InlineNotice>}<div className="settings-form-actions"><button type="submit" className="settings-button" disabled={!!pending || !currentPassword || newPassword.length < 12} onClick={event => { saveButton.current = event.currentTarget }}>Change password</button></div></form>
    </section>
    <section className="settings-section" aria-labelledby="settings-factor-title" aria-busy={pending === 'factor'}><header className="settings-section-heading"><h3 id="settings-factor-title">Two-step verification</h3><p>Use a code from an authenticator app as an extra sign-in check.</p></header>
      {error && !review && <InlineNotice error title={state ? 'Two-step verification needs attention' : 'Check your security status'} actions={!state && <button type="button" className="settings-button" disabled={!!pending} onClick={() => { setError(''); setAttempt(value => value + 1) }}>Reload security status</button>}>{error}</InlineNotice>}{notice && <InlineNotice>{notice}</InlineNotice>}
      {!state && !error && <LoadingState label="Checking sign-in protection…" compact />}
      {state && <>
        <div className="settings-status-row"><span className="settings-status" data-enabled={state.enabled}>{state.enabled ? 'Enabled' : 'Not enabled'}</span>{state.enabled && <span>{state.backup_codes_remaining} backup codes remaining</span>}</div>
        {state.locked && <InlineNotice error title="Authenticator attempts are locked">Recover your password to unlock attempts, or ask your administrator for a reset.</InlineNotice>}
        {session.second_factor_setup_required && <InlineNotice>A workspace requires two-step verification. Set it up now; your next sign-in will require it.</InlineNotice>}
      </>}
      {codes ? <BackupCodes codes={codes} onSaved={() => setCodes(null)} /> : state && <>
        {!state.enabled && !enrollment && <button type="button" className="settings-button" onClick={() => void start()} disabled={!!pending || state.locked}>{pending ? 'Preparing setup…' : state.pending_expires_at ? 'Start a new authenticator setup' : 'Set up authenticator'}</button>}
        {enrollment && <div className="settings-factor-setup"><AuthenticatorSetup enrollment={enrollment} /></div>}
        {(enrollment || action) && <form className="settings-factor-form" onSubmit={event => { event.preventDefault(); if (action) setReview(action); else void saveFactor() }}><fieldset disabled={!!pending}>
          {action && <div className="settings-field"><label htmlFor="factor-password">Current password</label><GlassInput id="factor-password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required maxLength={1024} /></div>}
          <div className="settings-field"><label htmlFor="factor-code">{action === 'disable' ? 'Authenticator or backup code' : 'Authenticator code'}</label><GlassInput id="factor-code" autoComplete="one-time-code" inputMode={action === 'disable' ? 'text' : 'numeric'} value={code} onChange={event => setCode(event.target.value)} required maxLength={64} aria-describedby="factor-code-hint" /><p id="factor-code-hint">{action === 'disable' ? 'Use a current authenticator code or an unused backup code.' : 'Enter the 6-digit code from your authenticator app.'}</p></div>
          {action && <p className="settings-help">{action === 'disable' ? 'Your authenticator and backup codes will be removed. Other sessions will be signed out.' : 'All existing backup codes will be replaced. Save the new set before leaving.'}</p>}
          <div className="settings-form-actions"><button type="button" className="settings-button" onClick={() => { setAction(null); setEnrollment(null); setPassword(''); setCode(''); setError('') }}>Cancel</button><button type="submit" className="settings-button settings-primary" onClick={event => { saveButton.current = event.currentTarget }} disabled={!code.trim() || (!!action && !password)}>{pending ? 'Verifying…' : action === 'disable' ? 'Review disable' : action === 'regenerate' ? 'Review replacement' : 'Enable two-step verification'}</button></div>
        </fieldset></form>}
        {state.enabled && !action && <div className="settings-form-actions"><button type="button" className="settings-button" disabled={!!pending || state.locked} onClick={() => { setAction('regenerate'); setError(''); setNotice('') }}>Replace backup codes</button><button type="button" className="settings-button settings-danger" disabled={!!pending || state.locked || policyRequired} onClick={() => { setAction('disable'); setError(''); setNotice('') }}>Disable two-step verification</button></div>}
        {state.enabled && policyRequired && <p className="settings-help">A workspace requires two-step verification, so it cannot be disabled.</p>}
      </>}
      {state && <p className="settings-footnote">{state.security_emails_available ? 'Account security changes send an email notice.' : 'Security email notices are unavailable on this site. Security changes still take effect.'}</p>}
    </section>
    <SettingsConfirmation open={review !== null} title={review === 'password' ? 'Change your password?' : review === 'disable' ? 'Disable two-step verification?' : 'Replace your backup codes?'} description={review === 'password' ? 'Every active session will end. Sign in again with your new password to continue.' : review === 'disable' ? 'Your authenticator and backup codes will be removed, and other sessions will be signed out.' : 'Your existing backup codes will stop working. Save the new codes shown after this change.'}
      pending={!!pending} dirty={!!(currentPassword || newPassword || enrollment || action || codes)} error={review === 'password' ? passwordError : error} confirmLabel={review === 'password' ? 'Change password' : review === 'disable' ? 'Confirm disable' : 'Replace codes'} danger onCancel={() => setReview(null)} onConfirm={() => { if (review === 'password') void savePassword(); else void saveFactor() }} returnFocus={saveButton}
      navigationWarning={codes ? { title: 'Save your backup codes', description: 'These codes are shown only once. Save them somewhere private before leaving this page.', leaveLabel: 'Leave without saving codes' } : undefined} />
  </>
}
