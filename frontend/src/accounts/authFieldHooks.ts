import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

/**
 * Disabling a fieldset while a request runs can drop keyboard focus to the page.
 * Remember the focused control on submit and return to it once the request settles.
 */
export function usePendingFocus(pending: boolean) {
  const saved = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (pending) return
    const element = saved.current
    saved.current = null
    const active = document.activeElement
    if (element?.isConnected && (!active || active === document.body)) element.focus()
  }, [pending])
  return {
    remember() {
      const active = document.activeElement
      saved.current = active instanceof HTMLElement && active !== document.body ? active : null
    },
    forget() {
      saved.current = null
    },
  }
}

/** Caps Lock is a common cause of rejected passwords; report it while a password field has focus. */
export function useCapsLock() {
  const [capsLock, setCapsLock] = useState(false)
  function read(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState('CapsLock'))
  }
  return {
    capsLock,
    capsLockProps: { onKeyDown: read, onKeyUp: read, onBlur: () => setCapsLock(false) },
  }
}

/** Mirrors backend/app/accounts/security.py: 12 to 1024 characters, counted as code points. */
export const PASSWORD_MIN_LENGTH = 12

export function passwordLongEnough(value: string) {
  return Array.from(value).length >= PASSWORD_MIN_LENGTH
}
