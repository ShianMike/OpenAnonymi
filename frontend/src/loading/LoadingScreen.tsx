import { useEffect, useState, type CSSProperties } from 'react'
import { useLoadingAwareness } from './useLoadingAwareness'
import { useLoadingPresence } from './foregroundLoading'
import { BootArt, BootFrame } from './BootFrame'
import { replacesLoadingScreen, trackLoadingScreen, type BootTone } from './bootScreen'
import './loading.css'

export function LoadingScreen({ label, description, tone }: { label: string; description: string; tone?: BootTone }) {
  const { ref, slow, offline } = useLoadingAwareness()
  useLoadingPresence(ref, true)
  // Animations count from page load, so a screen that replaces another continues the same frame.
  const [start] = useState(() => ({
    replacing: replacesLoadingScreen(),
    alreadySlow: document.getElementById('startup-loading')?.dataset.slow === 'true',
    offset: -Math.round(performance.now()),
  }))
  useEffect(trackLoadingScreen, [])
  const waiting = slow || offline || start.alreadySlow
  const message = offline ? 'You appear to be offline. Reconnect, then reload to open OpenAnonymi.'
    : waiting ? 'Taking longer than usual to open. You can reload if the connection was interrupted.' : description
  return <BootFrame tone={tone} frameRef={ref} entrance={!start.replacing} slow={waiting}
    style={{ '--boot-offset': `${start.offset}ms` } as CSSProperties}>
    <BootArt />
    <div className="boot-status" role="status" aria-atomic="true">
      <h1>{label}</h1>
      <p>{message}</p>
    </div>
    <button className="boot-retry" type="button" onClick={() => window.location.reload()}>Reload this page</button>
  </BootFrame>
}
