import { useId, type ReactNode } from 'react'
import './disabled-reason.css'

/** Disabled native buttons remain disabled; their explanation supports keyboard focus. */
export function DisabledReason({ disabled, reason, children }: {
  disabled: boolean
  reason: string
  children: ReactNode
}) {
  const id = useId()
  return <span className="disabled-reason" tabIndex={disabled ? 0 : undefined}
    aria-describedby={disabled ? id : undefined}>
    {children}
    {disabled && <span id={id} className="disabled-reason-tooltip" role="tooltip">{reason}</span>}
  </span>
}
