import { useEffect, useRef, useState } from 'react'
import './border-beam.css'

/** Decorative edge light for a positioned, rounded field or panel. */
export function BorderBeam({ active = true }: { active?: boolean }) {
  const rimRef = useRef<HTMLSpanElement>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const rim = rimRef.current
    if (!rim) return
    // Keep travel speed steady when a large field is resized. The CSS motion
    // path follows the host's dimensions and radius without rebuilding a path.
    const resize = new ResizeObserver(([entry]) => {
      const box = entry.borderBoxSize?.[0]
      const { width, height } = box
        ? { width: box.inlineSize, height: box.blockSize }
        : rim.getBoundingClientRect()
      const radius = Math.min(
        parseFloat(getComputedStyle(rim).borderTopLeftRadius) || 0,
        width / 2,
        height / 2,
      )
      const perimeter = 2 * (width + height) - (8 - 2 * Math.PI) * radius
      rim.style.setProperty('--beam-duration', `${Math.max(4, perimeter / 140)}s`)
    })
    const visibility = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting))
    resize.observe(rim, { box: 'border-box' })
    visibility.observe(rim)
    return () => {
      resize.disconnect()
      visibility.disconnect()
    }
  }, [])

  return (
    <span ref={rimRef} className="border-beam" aria-hidden="true" data-active={active} data-in-view={inView}>
      <span className="border-beam-light" />
    </span>
  )
}
