import { Children, isValidElement, type OptionHTMLAttributes, type ReactNode } from 'react'
import * as Select from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import './glass-select.css'

type OptionProps = OptionHTMLAttributes<HTMLOptionElement> & { 'data-description'?: string }
type Props = {
  id: string
  value: string | number
  onValueChange: (value: string) => void
  children: ReactNode
  displayValue?: ReactNode
  disabled?: boolean
  className?: string
  'aria-label'?: string
  'aria-describedby'?: string
}

function optionText(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child) ? optionText(child.props.children) : String(child),
    )
    .join('')
}

/** Controlled single selection; accepts readable option children at each form's call site. */
export function GlassSelect({
  id,
  value,
  onValueChange,
  children,
  displayValue,
  disabled,
  className = '',
  ...aria
}: Props) {
  const options = Children.toArray(children)
    .filter((child) => isValidElement<OptionProps>(child) && child.type === 'option')
    .map((child) => {
      const props = (child as React.ReactElement<OptionProps>).props
      return { ...props, value: String(props.value ?? optionText(props.children)) }
    })
  const selected = options.find((option) => option.value === String(value))

  // Radix reserves the empty string for a placeholder. Prefix all values so an
  // explicit empty option (e.g. Custom settings) remains selectable and distinct.
  return (
    <Select.Root
      value={`option:${value}`}
      onValueChange={(next) => onValueChange(next.slice(7))}
      disabled={disabled}
    >
      <Select.Trigger id={id} className={`glass-select-trigger ${className}`} {...aria}>
        <span className="glass-select-value" title={optionText(selected?.children)}>
          <Select.Value>{displayValue ?? selected?.children ?? 'Choose an option'}</Select.Value>
        </span>
        <Select.Icon className="glass-select-chevron">
          <ChevronDown size={16} aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="glass-select-menu" position="popper" sideOffset={8} collisionPadding={12}>
          <Select.Viewport className="glass-select-options">
            {options.map((option) => (
              <Select.Item
                key={option.value}
                value={`option:${option.value}`}
                disabled={option.disabled}
                textValue={optionText(option.children)}
                className="glass-select-option"
              >
                <span className="glass-select-option-copy">
                  <Select.ItemText>{option.children}</Select.ItemText>
                  {option['data-description'] && (
                    <span className="glass-select-description">{option['data-description']}</span>
                  )}
                </span>
                <span className="glass-select-check">
                  <Select.ItemIndicator>
                    <Check size={14} strokeWidth={2.4} aria-hidden="true" />
                  </Select.ItemIndicator>
                </span>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  )
}
