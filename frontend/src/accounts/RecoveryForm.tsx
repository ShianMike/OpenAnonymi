import { LoadingMark } from '../loading/LoadingMark'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowUpRight, AtSign, KeyRound, LockKeyhole } from 'lucide-react'
import { completeRecovery, requestRecovery } from '../api/client'
import { GlassInput } from '../ui/GlassField'
import { AuthNotice, CapsLockNote, PasswordRequirement } from './AuthNotice'
import { PASSWORD_MIN_LENGTH, useCapsLock, usePendingFocus } from './authFieldHooks'

export type RecoveryStep = 'request' | 'code'
type Action = 'request' | 'resend' | 'complete'

function field(id: string) {
  return document.getElementById(id) as HTMLInputElement | null
}

export function RecoveryForm({
  initialEmail = '',
  onStepChange,
  onComplete,
}: {
  initialEmail?: string
  onStepChange: (step: RecoveryStep) => void
  onComplete: (email: string) => void
}) {
  const [email, setEmail] = useState(initialEmail)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [step, setStep] = useState<RecoveryStep>('request')
  // False when someone skips ahead with a code they already have (recovery or invitation email).
  const [requested, setRequested] = useState(false)
  const [pending, setPending] = useState<Action | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const focus = usePendingFocus(pending !== null)
  const { capsLock, capsLockProps } = useCapsLock()
  const onCode = step === 'code'

  // Focus waits for the render where the next step's field exists and is enabled again.
  const focusNext = useRef<string | null>(null)
  useEffect(() => {
    const element = focusNext.current ? field(focusNext.current) : null
    if (!element || element.matches(':disabled')) return
    focusNext.current = null
    element.focus()
  })

  function goTo(next: RecoveryStep, focusId: string) {
    setStep(next)
    onStepChange(next)
    focusNext.current = focusId
  }

  async function run(action: Action) {
    if (pending) return
    if (action === 'resend' && !field('recovery-email')?.reportValidity()) return
    focus.remember()
    setPending(action)
    setError(null)
    try {
      if (action === 'complete') {
        // Codes never contain whitespace; pasted copies from email often do.
        await completeRecovery(email, code.replace(/\s/g, ''), password)
        setPassword('')
        onComplete(email)
        return
      }
      const result = await requestRecovery(email)
      setNotice(requested ? `Requested again. ${result.message}` : result.message)
      setRequested(true)
      if (action === 'resend') setCode('')
      if (!onCode) {
        focus.forget()
        goTo('code', 'recovery-code')
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Recovery could not be completed.')
    } finally {
      setPending(null)
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run(onCode ? 'complete' : 'request')
  }

  function changeEmail() {
    setRequested(false)
    setNotice(null)
    setError(null)
    setCode('')
    goTo('request', 'recovery-email')
  }

  function enterCode() {
    setNotice(null)
    setError(null)
    // Without a request the email may still be empty.
    goTo('code', email ? 'recovery-code' : 'recovery-email')
  }

  const passwordNotes = ['recovery-password-hint', capsLock && 'recovery-password-caps'].filter(Boolean).join(' ')
  const busy = pending !== null

  return (
    <form onSubmit={submit} className="auth-form" aria-busy={busy}>
      {notice && <AuthNotice tone="sent">{notice}</AuthNotice>}
      {error && <AuthNotice tone="error">{error}</AuthNotice>}
      <fieldset disabled={busy} className="auth-fields">
        <div className="auth-field-row">
          <div className="auth-label-row">
            <label htmlFor="recovery-email">Account email</label>
            {onCode && requested && (
              <button type="button" className="auth-link" onClick={changeEmail}>
                Change email
              </button>
            )}
          </div>
          <GlassInput
            id="recovery-email"
            type="email"
            icon={AtSign}
            autoComplete="username"
            required
            maxLength={320}
            placeholder="you@example.com"
            value={email}
            readOnly={onCode && requested}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        {onCode && (
          <>
            <div className="auth-field-row">
              <label htmlFor="recovery-code">Code from email</label>
              <GlassInput
                id="recovery-code"
                className="auth-code-field"
                icon={KeyRound}
                autoComplete="one-time-code"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                required
                maxLength={200}
                aria-describedby="recovery-code-hint"
                placeholder="Paste the code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
              <small id="recovery-code-hint" className="field-hint">
                Recovery codes expire after 30 minutes.
              </small>
            </div>
            <div className="auth-field-row">
              <label htmlFor="recovery-password">New password</label>
              <GlassInput
                id="recovery-password"
                icon={LockKeyhole}
                type="password"
                required
                autoComplete="new-password"
                minLength={PASSWORD_MIN_LENGTH}
                maxLength={1024}
                aria-describedby={passwordNotes}
                placeholder="Choose a new password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                {...capsLockProps}
              />
              <PasswordRequirement id="recovery-password-hint" value={password} />
              <CapsLockNote id="recovery-password-caps" on={capsLock} />
            </div>
          </>
        )}
        <button type="submit" className="auth-submit">
          <span className="auth-submit-label">
            {(pending === 'request' || pending === 'complete') && <LoadingMark small />}
            {pending === 'complete'
              ? 'Changing your password…'
              : pending === 'request'
                ? 'Sending recovery code…'
                : onCode
                  ? 'Change password'
                  : 'Send recovery code'}
          </span>
          {pending !== 'request' && pending !== 'complete' && <ArrowUpRight size={18} aria-hidden="true" />}
        </button>
        {onCode ? (
          <p className="auth-resend">
            <span>{requested ? 'No email yet?' : 'Need a code?'}</span>
            <button type="button" className="auth-link" onClick={() => void run('resend')}>
              {pending === 'resend' ? 'Sending a code…' : requested ? 'Send a new code' : 'Send me a code'}
            </button>
          </p>
        ) : (
          <p className="auth-resend">
            <span>Have a code from an email?</span>
            <button type="button" className="auth-link" onClick={enterCode}>
              Enter a code
            </button>
          </p>
        )}
      </fieldset>
      {busy && (
        <span className="sr-only" role="status">
          {pending === 'complete' ? 'Changing password' : 'Sending recovery code'}
        </span>
      )}
    </form>
  )
}
