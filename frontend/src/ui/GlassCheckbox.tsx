import { useId } from 'react'
import * as Checkbox from '@radix-ui/react-checkbox'
import { Check } from 'lucide-react'
import './glass-checkbox.css'

export function GlassCheckbox({
  id,
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  id?: string
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  const generatedId = useId()
  const controlId = id ?? generatedId
  return (
    <div className="glass-checkbox-row" data-disabled={disabled || undefined}>
      <Checkbox.Root
        id={controlId}
        className="glass-checkbox-control"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        aria-labelledby={`${controlId}-label`}
        aria-describedby={description ? `${controlId}-description` : undefined}
      >
        <Checkbox.Indicator className="glass-checkbox-indicator">
          <Check size={14} strokeWidth={2.5} aria-hidden="true" />
        </Checkbox.Indicator>
      </Checkbox.Root>
      <label htmlFor={controlId}>
        <span id={`${controlId}-label`}>{label}</span>
        {description && <small id={`${controlId}-description`}>{description}</small>}
      </label>
    </div>
  )
}
