import { LoadingMark } from '../loading/LoadingMark'
import { useState, type FormEvent } from 'react'
import { AtSign, KeyRound, LockKeyhole } from 'lucide-react'
import { completeRecovery, requestRecovery } from '../api/client'
import { GlassInput } from '../ui/GlassField'

export function RecoveryForm({ onComplete }: { onComplete: () => void }) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [sent, setSent] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      if (sent) {
        await completeRecovery(email, code, password)
        setPassword('')
        onComplete()
      } else {
        const result = await requestRecovery(email)
        setNotice(result.message)
        setSent(true)
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Recovery could not be completed.')
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
      {notice && (
        <p role="status" className="auth-notice">
          {notice}
        </p>
      )}
      <fieldset disabled={pending} className="auth-fields">
        <div className="auth-field-row">
          <label htmlFor="recovery-email">Account email</label>
          <GlassInput
            id="recovery-email"
            type="email"
            icon={AtSign}
            autoComplete="email"
            required
            value={email}
            readOnly={sent}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        {sent && (
          <>
            <div className="auth-field-row">
              <label htmlFor="recovery-code">Code from email</label>
              <GlassInput
                id="recovery-code"
                icon={KeyRound}
                autoComplete="one-time-code"
                required
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </div>
            <div className="auth-field-row">
              <label htmlFor="recovery-password">New password</label>
              <GlassInput
                id="recovery-password"
                icon={LockKeyhole}
                type="password"
                required
                autoComplete="new-password"
                minLength={12}
                maxLength={1024}
                aria-describedby="recovery-password-hint"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <small id="recovery-password-hint" className="field-hint">
                Use at least 12 characters.
              </small>
            </div>
          </>
        )}
        <button type="submit" className="auth-submit">
          {pending ? <><LoadingMark small /> {sent ? 'Changing your password…' : 'Sending recovery code…'}</> : sent ? 'Change password' : 'Send recovery code'}
        </button>
        {sent && (
          <button
            type="button"
            className="auth-link"
            onClick={() => {
              setSent(false)
              setNotice(null)
            }}
          >
            Use a different email or resend code
          </button>
        )}
      </fieldset>
    </form>
  )
}
