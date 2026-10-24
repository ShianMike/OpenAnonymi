import { useEffect, useSyncExternalStore, type RefObject } from 'react'

let count = 0
const listeners = new Set<() => void>()
const publish = () => listeners.forEach(listener => listener())
const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

/** Avoid duplicate background feedback while a visible section already announces loading. */
export const useForegroundLoading = () => useSyncExternalStore(subscribe, () => count > 0)
export function useLoadingPresence(ref: RefObject<HTMLElement | null>, present: boolean) {
  useEffect(() => {
    if (!present || !ref.current) return
    let registered = false
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting === registered) return
      registered = entry.isIntersecting
      count += registered ? 1 : -1
      publish()
    })
    observer.observe(ref.current)
    return () => {
      observer.disconnect()
      if (registered) { count -= 1; publish() }
    }
  }, [ref, present])
}
