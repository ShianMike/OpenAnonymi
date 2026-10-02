import { useState, type ComponentPropsWithRef } from 'react'
import { BorderBeam } from './BorderBeam'
import './glass-textarea.css'

/** Keeps the native textarea, selection, ref and resize handle intact. */
export function GlassTextarea({ onFocus, onBlur, ...props }: ComponentPropsWithRef<'textarea'>) {
  const [focused, setFocused] = useState(false)
  return (
    <div className="glass-textarea">
      <textarea
        {...props}
        onFocus={(event) => {
          setFocused(true)
          onFocus?.(event)
        }}
        onBlur={(event) => {
          setFocused(false)
          onBlur?.(event)
        }}
      />
      <BorderBeam active={focused && !props.disabled} />
    </div>
  )
}
