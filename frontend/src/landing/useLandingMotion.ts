import { useEffect, useRef, useState } from 'react'
import { useDisplayPreferences } from '../appearance/useDisplayPreferences'

const REVEAL = '[data-landing-reveal]'

/** Reveals sections once as they enter view and reports when the page has scrolled past the top. */
export function useLandingMotion() {
  const root = useRef<HTMLDivElement>(null)
  const sentinel = useRef<HTMLSpanElement>(null)
  const [scrolled, setScrolled] = useState(false)
  const { reducedMotion } = useDisplayPreferences()

  useEffect(() => {
    const element = root.current
    if (!element || reducedMotion || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        if (!isIntersecting || !(target instanceof HTMLElement)) return
        target.dataset.revealed = 'true'
        observer.unobserve(target)
      })
    }, { threshold: 0.12, rootMargin: '0px 0px -4% 0px' })
    // The page is static, so every reveal target exists on mount.
    element.querySelectorAll<HTMLElement>(REVEAL).forEach((target) => {
      if (target.dataset.revealed !== 'true') observer.observe(target)
    })
    element.dataset.motionReady = 'true'
    return () => {
      observer.disconnect()
      delete element.dataset.motionReady
    }
  }, [reducedMotion])

  useEffect(() => {
    const marker = sentinel.current
    if (!marker || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting))
    observer.observe(marker)
    return () => observer.disconnect()
  }, [])

  return { root, sentinel, scrolled }
}
