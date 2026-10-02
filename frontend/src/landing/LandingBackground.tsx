import { useEffect } from 'react'
import { motion, useSpring } from 'motion/react'
import './background.css'

/** Layered, independently drifting light creates a flowing silk surface. */
export function LandingBackground({ paused }: { paused: boolean }) {
  const x = useSpring(0, { stiffness: 180, damping: 26 })
  const y = useSpring(0, { stiffness: 180, damping: 26 })

  useEffect(() => {
    if (paused) {
      x.jump(0)
      y.jump(0)
      return
    }
    const onPointer = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' || document.hidden) return
      x.set((event.clientX / window.innerWidth - .5) * 34)
      y.set((event.clientY / window.innerHeight - .5) * 28)
    }
    const reset = () => { x.jump(0); y.jump(0) }
    window.addEventListener('pointermove', onPointer, { passive: true })
    window.addEventListener('blur', reset)
    document.addEventListener('visibilitychange', reset)
    return () => {
      window.removeEventListener('pointermove', onPointer)
      window.removeEventListener('blur', reset)
      document.removeEventListener('visibilitychange', reset)
      x.stop()
      y.stop()
    }
  }, [paused, x, y])

  return (
    <div className="landing-background landing-loop-scene" aria-hidden="true">
      <motion.div className="landing-background-pointer" style={{ x, y }}>
        <div className="landing-silk-layer landing-silk-depth" />
        <div className="landing-silk-layer landing-silk-light" />
        <div className="landing-silk-layer landing-silk-ribbon" />
      </motion.div>
      <div className="landing-silk-grain" />
    </div>
  )
}
