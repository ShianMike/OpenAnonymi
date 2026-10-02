import { useState, type InputHTMLAttributes } from 'react'
import { Eye, EyeOff, type LucideIcon } from 'lucide-react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & { icon?: LucideIcon }

/** Native form semantics; the light is decorative and confined to the glass rim. */
export function GlassInput({ icon: Icon, type, className = '', ...props }: InputProps) {
  const [visible, setVisible] = useState(false)
  const password = type === 'password'
  return (
    <div className={`glass-field ${Icon ? 'glass-field--icon' : ''} ${className}`}>
      {Icon && <Icon className="glass-field-icon" size={17} aria-hidden="true" />}
      <input
        {...props}
        type={password && visible ? 'text' : type}
        className={password ? 'glass-password' : undefined}
      />
      {password && (
        <button
          className="password-toggle"
          type="button"
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
          disabled={props.disabled}
          onClick={() => setVisible((value) => !value)}
        >
          {visible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
        </button>
      )}
    </div>
  )
}
