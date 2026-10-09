import { useState, type FormEvent } from 'react'
import { ArrowRight, CheckCircle2, Mail } from 'lucide-react'
import { confirmEmailVerification, getSession, requestEmailVerification, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice } from '../../ui/WorkspaceControls'

export function EmailVerification({ session, onVerified }: {
  session: SessionView; onVerified: (session: SessionView) => void
}) {
  const [requested, setRequested] = useState(false)
  const [code, setCode] = useState('')
  const [pending, setPending] = useState<'request' | 'confirm' | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<{ action: 'request' | 'confirm'; message: string } | null>(null)
  async function request() {
    if (pending) return
    setPending('request'); setError(null); setNotice(null)
    try {
      const result = await requestEmailVerification(session.csrf_token)
      setNotice(result.message); setRequested(true); setCode('')
      requestAnimationFrame(() => document.getElementById('email-verification-code')?.focus())
    } catch (cause) { setError({ action: 'request', message: cause instanceof Error ? cause.message : 'Code could not be sent.' }) }
    finally { setPending(null) }
  }
  async function confirm(event: FormEvent) {
    event.preventDefault()
    if (pending || !code.trim()) return
    setPending('confirm'); setError(null)
    try {
      await confirmEmailVerification(code.replace(/\s/g, ''), session.csrf_token)
      const current = await getSession()
      onVerified(current); setCode(''); setRequested(false); setNotice(null)
    } catch (cause) { setError({ action: 'confirm', message: cause instanceof Error ? cause.message : 'Code could not be verified.' }) }
    finally { setPending(null) }
  }
  return <section className="email-verification" aria-labelledby="account-email-title" aria-busy={!!pending}>
    <div className="email-verification-heading">
      <span className="email-verification-icon"><Mail size={20} aria-hidden="true" /></span>
      <div className="account-email"><h3 id="account-email-title">Email address</h3><strong>{session.email}</strong></div>
      <span className="email-verification-status" data-verified={session.email_verified}>
        {session.email_verified && <CheckCircle2 size={14} aria-hidden="true" />}
        {session.email_verified ? 'Verified' : 'Not verified'}
      </span>
    </div>
    {session.email_verified ? <p className="email-verification-help" role="status">Your email address is verified.</p> : <>
      {requested ? <div className="email-verification-entry">
        <div><h4>Check your inbox</h4><p className="email-verification-help" id="email-verification-help">Paste the code from your verification email. Use the latest code; it expires after 15 minutes.</p></div>
        <form onSubmit={confirm} className="email-verification-form">
          <div><label className="field-label" htmlFor="email-verification-code">Email verification code</label>
            <GlassInput id="email-verification-code" autoComplete="one-time-code" autoCapitalize="none" spellCheck={false}
              placeholder="Paste your verification code" required maxLength={200} disabled={!!pending} value={code}
              aria-describedby={`email-verification-help${error?.action === 'confirm' ? ' email-verification-error' : ''}`}
              aria-invalid={error?.action === 'confirm'} onChange={event => { setCode(event.target.value); setError(null) }} />
          </div>
          {error && <div id="email-verification-error"><InlineNotice error>{error.message}</InlineNotice></div>}
          <div className="email-verification-actions">
            <button type="submit" className="button-primary" disabled={!!pending || !code.trim()}>
              {pending === 'confirm' ? 'Verifying…' : 'Verify email'}<ArrowRight size={16} aria-hidden="true" />
            </button>
            {session.email_verification_available && <button type="button" className="button-secondary" disabled={!!pending} onClick={() => void request()}>
              {pending === 'request' ? 'Sending code…' : 'Send a new code'}
            </button>}
          </div>
        </form>
        <p className="email-verification-notice" role="status">{notice || 'Didn’t receive a code? Check your spam folder or send a new one.'}</p>
      </div> : <div className="email-verification-start">
        <p className="email-verification-help">{session.email_verification_available ? 'Confirm this address is yours with a code sent to your inbox.' : 'Email verification is unavailable right now. You can try again when email delivery returns.'}</p>
        {session.email_verification_available && <div className="email-verification-actions">
          <button type="button" className="button-primary" disabled={!!pending} onClick={() => void request()}>
            {pending === 'request' ? 'Sending code…' : 'Verify your email'}<ArrowRight size={16} aria-hidden="true" />
          </button>
          <button type="button" className="button-secondary" disabled={!!pending} onClick={() => {
            setRequested(true); setError(null)
            requestAnimationFrame(() => document.getElementById('email-verification-code')?.focus())
          }}>Enter a code</button>
        </div>}
        {error && <InlineNotice error>{error.message}</InlineNotice>}
      </div>}
    </>}
  </section>
}
