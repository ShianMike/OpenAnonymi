import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
const subscribe = (listener: () => void) => {
  reducedMotion.addEventListener('change', listener)
  return () => reducedMotion.removeEventListener('change', listener)
}

export function useLandingMotion() {
  const root = useRef<HTMLDivElement>(null)
  const [paused, setPaused] = useState(false)
  const reduced = useSyncExternalStore(subscribe, () => reducedMotion.matches)

  useEffect(() => {
    const element = root.current
    if (!element || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        const targetElement = target as HTMLElement
        targetElement.dataset.visible = String(isIntersecting)
        if (isIntersecting) targetElement.dataset.revealed = 'true'
      })
    }, { threshold: 0.08 })
    const selector = '[data-landing-reveal], .landing-loop-scene'
    const track = (node: Node, adding: boolean) => {
      if (!(node instanceof Element)) return
      const targets = Array.from(node.querySelectorAll(selector))
      if (node.matches(selector)) targets.push(node)
      targets.forEach((target) => adding ? observer.observe(target) : observer.unobserve(target))
    }
    track(element, true)
    const changes = new MutationObserver((records) => records.forEach((record) => {
      record.removedNodes.forEach((node) => track(node, false))
      record.addedNodes.forEach((node) => track(node, true))
    }))
    changes.observe(element, { childList: true, subtree: true })
    element.dataset.motionReady = 'true'
    const onVisibility = () => { element.dataset.pageVisible = String(!document.hidden) }
    onVisibility()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      observer.disconnect()
      changes.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      delete element.dataset.motionReady
    }
  }, [])

  return { root, paused: paused || reduced, reduced, toggleMotion: () => setPaused((value) => !value) }
}
