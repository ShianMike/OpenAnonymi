import { useId } from 'react'
import { useLoadingMotion } from './useLoadingMotion'

/** A folded page with two travelling lights; decorative, never a fake percentage. */
export function LoadingMark({ small = false }: { small?: boolean }) {
  const id = useId()
  const ref = useLoadingMotion<HTMLSpanElement>()
  return <span ref={ref} className={small ? 'loading-mark loading-mark-small' : 'loading-mark'} aria-hidden="true">
    <svg viewBox="0 0 64 64" fill="none" focusable="false">
      <defs><linearGradient id={id} x1="19" y1="15" x2="44" y2="50" gradientUnits="userSpaceOnUse">
        <stop stopColor="var(--loading-shine)" /><stop offset="1" stopColor="var(--loading-depth)" />
      </linearGradient></defs>
      <circle cx="32" cy="32" r="29" className="loading-mark-track" />
      <g className="loading-mark-orbit">
        <path d="M8 16a29 29 0 0 1 28-13M56 48a29 29 0 0 1-28 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="60" cy="23" r="2.4" fill="currentColor" />
      </g>
      <g className="loading-mark-page">
        <path d="M22 15h15l9 9v23a3 3 0 0 1-3 3H22a3 3 0 0 1-3-3V18a3 3 0 0 1 3-3Z" fill={`url(#${id})`} />
        <path d="M37 15v9h9" stroke="var(--loading-ink)" strokeOpacity=".45" strokeWidth="1.3" />
        <path d="M25 30h13M25 36h13M25 42h8" stroke="var(--loading-ink)" strokeWidth="1.8" strokeLinecap="round" />
      </g>
    </svg>
  </span>
}
