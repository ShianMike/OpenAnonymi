import { useEffect, useRef } from 'react'

export function useLoadingMotion<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    const element = ref.current
    let visible = true
    const sync = () => element?.setAttribute('data-motion', String(visible && !document.hidden))
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    if (element) observer.observe(element)
    document.addEventListener('visibilitychange', sync)
    sync()
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', sync) }
  }, [])
  return ref
}
