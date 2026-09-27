import { useState, type FormEvent } from 'react'
import {
  completeRecovery, requestRecovery, signIn, type SessionView,
} from '../api/client'

type Props = { onSignedIn: (session: SessionView) => void }

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

export function SignInPage({ onSignedIn }: Props) {
  const [mode, setMode] = useState<'sign-in' | 'recovery'>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function submitSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const session = await signIn(email, password)
      setPassword('')
      onSignedIn(session)
    } catch (cause: unknown) {
      setPassword('')
      setError(messageFrom(cause))
    } finally {
      setPending(false)
    }
  }

  async function sendCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    setNotice(null)
    try {
      const result = await requestRecovery(email)
      setNotice(result.message)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setPending(false)
    }
  }

  async function resetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await completeRecovery(email, code, newPassword)
      setCode('')
      setNewPassword('')
      setMode('sign-in')
      setNotice('Password changed. Sign in with your new password.')
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setPending(false)
    }
  }

  return (
    <main id="main-content" className="auth-page">
      <h1>{mode === 'sign-in' ? 'Sign in' : 'Recover account'}</h1>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {mode === 'sign-in' ? (
        <>
          <form onSubmit={submitSignIn}>
            <label htmlFor="sign-in-email">Email</label>
            <input id="sign-in-email" type="email" autoComplete="username" required
              value={email} onChange={(event) => setEmail(event.target.value)} />
            <label htmlFor="sign-in-password">Password</label>
            <input id="sign-in-password" type="password" autoComplete="current-password" required
              value={password} onChange={(event) => setPassword(event.target.value)} />
            <button type="submit" disabled={pending}>{pending ? 'Signing in…' : 'Sign in'}</button>
          </form>
          <button type="button" onClick={() => {
            setError(null)
            setNotice(null)
            setMode('recovery')
          }}>Recover account</button>
        </>
      ) : (
        <>
          <p>Enter your account email to request a one-time code. Delivery must be configured by the workspace operator.</p>
          <form onSubmit={sendCode}>
            <label htmlFor="recovery-email">Account email</label>
            <input id="recovery-email" type="email" autoComplete="email" required
              value={email} onChange={(event) => setEmail(event.target.value)} />
            <button type="submit" disabled={pending}>{pending ? 'Requesting…' : 'Request code'}</button>
          </form>
          <form onSubmit={resetPassword}>
            <label htmlFor="recovery-code">Code from email</label>
            <input id="recovery-code" type="text" autoComplete="one-time-code" required
              value={code} onChange={(event) => setCode(event.target.value)} />
            <label htmlFor="new-password">New password (at least 12 characters)</label>
            <input id="new-password" type="password" autoComplete="new-password" minLength={12} required
              value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
            <button type="submit" disabled={pending}>{pending ? 'Changing…' : 'Change password'}</button>
          </form>
          <button type="button" onClick={() => {
            setError(null)
            setMode('sign-in')
          }}>Back to sign in</button>
        </>
      )}
    </main>
  )
}
