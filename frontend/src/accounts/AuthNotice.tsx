import type { ReactNode } from 'react'
import { Check, CircleAlert, CircleCheck, Info, MailCheck } from 'lucide-react'
import { passwordLongEnough, PASSWORD_MIN_LENGTH } from './authFieldHooks'

const icons = { error: CircleAlert, success: CircleCheck, sent: MailCheck, info: Info }

/** Errors interrupt (alert); confirmations and session messages wait their turn (status). */
export function AuthNotice({ tone, children }: { tone: keyof typeof icons; children: ReactNode }) {
  const Icon = icons[tone]
  return (
    <div className={`auth-notice auth-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
      <p>{children}</p>
    </div>
  )
}

/** Live length check for new passwords; the rule itself is enforced by the field and the API. */
export function PasswordRequirement({ id, value, tip }: { id: string; value: string; tip?: string }) {
  const met = passwordLongEnough(value)
  return (
    <p id={id} className="auth-requirement" data-met={met ? 'true' : undefined}>
      <span className="auth-requirement-mark" aria-hidden="true">
        {met && <Check size={11} strokeWidth={3} />}
      </span>
      <span>
        At least {PASSWORD_MIN_LENGTH} characters.{tip ? ` ${tip}` : ''}
        {met && <span className="sr-only"> Length requirement met.</span>}
      </span>
    </p>
  )
}

/** Empty until Caps Lock is detected, so the polite live region exists before it speaks. */
export function CapsLockNote({ id, on }: { id: string; on: boolean }) {
  return (
    <p id={id} className="auth-caps" aria-live="polite">
      {on ? 'Caps Lock is on.' : ''}
    </p>
  )
}
