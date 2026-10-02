import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { CheckCircle2, AlertCircle, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import './workspace-controls.css'


export function PanelHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon
  title: string
  description?: string
}) {
  return (
    <div className="panel-heading">
      <span className="panel-heading-icon">
        <Icon size={19} strokeWidth={1.6} aria-hidden="true" />
      </span>
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
    </div>
  )
}

export function ChoiceSwitch({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="choice-switch">
      <span>
        <strong>{label}</strong>
        {description && <small>{description}</small>}
      </span>
      <input
        type="checkbox"
        role="switch"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  )
}

export function InlineNotice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  const Icon = error ? AlertCircle : CheckCircle2
  return (
    <div className={`inline-notice${error ? ' is-error' : ''}`} role={error ? 'alert' : 'status'}>
      <Icon size={16} aria-hidden="true" />
      <div>{children}</div>
    </div>
  )
}

/** Used inside a Radix Dialog.Root so triggers retain native focus restoration. */
export function DialogFrame({
  title,
  description,
  busy,
  children,
  onCloseAutoFocus,
}: {
  title: string
  description: string
  busy?: boolean
  children: ReactNode
  onCloseAutoFocus?: (event: Event) => void
}) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="workspace-dialog-overlay" />
      <Dialog.Content
        aria-busy={busy}
        className="workspace-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
        onInteractOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => {
          if (busy) event.preventDefault()
        }}
      >
        <Dialog.Close className="quiet-icon dialog-close" aria-label="Close dialog" disabled={busy}>
          <X size={18} aria-hidden="true" />
        </Dialog.Close>
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description>{description}</Dialog.Description>
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  )
}
