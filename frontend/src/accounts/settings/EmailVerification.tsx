import { useState, type FormEvent } from 'react'
import { confirmEmailVerification, getSession, requestEmailVerification, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'

export function EmailVerification({ session }: { session: SessionView }) {
  const [verified, setVerified] = useState(session.email_verified)
  const [requested, setRequested] = useState(false)
  const [code, setCode] = useState('')
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  async function request() {
    setPending(true); setError(null)
    try {
      const result = await requestEmailVerification(session.csrf_token)
      setNotice(result.message); setRequested(true)
      requestAnimationFrame(() => document.getElementById('email-verification-code')?.focus())
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Code could not be sent.') }
    finally { setPending(false) }
  }
  async function confirm(event: FormEvent) {
    event.preventDefault(); setPending(true); setError(null)
    try {
      await confirmEmailVerification(code, session.csrf_token)
      const current = await getSession()
      setVerified(current.email_verified); setCode(''); setRequested(false); setNotice('Email verified.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Code could not be verified.') }
    finally { setPending(false) }
  }
  return <div className="email-verification">
    <p>{verified ? 'Email verified' : 'Email not verified'}</p>
    {notice && <p role="status" className="field-hint">{notice}</p>}
    {error && <p role="alert" className="field-hint">{error}</p>}
    {!verified && <>
      {session.email_verification_available ? <button type="button" className="button-secondary"
        disabled={pending} onClick={() => void request()}>{pending ? 'Sending…' : requested ? 'Send a new code' : 'Verify your email'}</button>
        : <p className="field-hint">Email delivery is unavailable on this site right now.</p>}
      {requested && <form onSubmit={confirm} className="account-password-form">
        <label htmlFor="email-verification-code">Email verification code</label>
        <GlassInput id="email-verification-code" autoComplete="one-time-code" required maxLength={200}
          disabled={pending} value={code} onChange={(event) => setCode(event.target.value)} />
        <button type="submit" className="button-primary" disabled={pending || !code.trim()}>{pending ? 'Verifying…' : 'Confirm email code'}</button>
      </form>}
    </>}
  </div>
}
