import { useId, type CSSProperties } from 'react'
import { cn } from '../ui/cn'

export type AuthIllustrationKind = 'document' | 'scan' | 'clock'

/** Original miniature illustrations, with motion carried by separate SVG layers. */
export function AuthIllustration({ kind, size = 36, className }: {
  kind: AuthIllustrationKind; size?: number; className?: string
}) {
  const id = useId()
  const body = `url(#${id}-body)`
  const light = `url(#${id}-light)`
  return (
    <span className={cn('privacy-glyph', `privacy-glyph-${kind}`, className)}
      style={{ '--glyph-size': `${size}px` } as CSSProperties} aria-hidden="true">
      <svg viewBox="0 0 64 64" fill="none" focusable="false">
        <defs>
          <linearGradient id={`${id}-body`} x1="16" y1="8" x2="48" y2="58" gradientUnits="userSpaceOnUse">
            <stop stopColor="var(--glyph-light)" /><stop offset=".45" stopColor="var(--glyph-mid)" /><stop offset="1" stopColor="var(--glyph-deep)" />
          </linearGradient>
          <linearGradient id={`${id}-light`} x1="16" y1="14" x2="49" y2="49" gradientUnits="userSpaceOnUse">
            <stop stopColor="var(--glyph-shine)" /><stop offset="1" stopColor="var(--glyph-mid)" />
          </linearGradient>
          <clipPath id={`${id}-scan`}><rect x="18" y="17" width="28" height="32" rx="5" /></clipPath>
        </defs>
        {kind === 'document' && <>
          <path d="M18 17h21l10 10v26a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4V21a4 4 0 0 1 4-4Z" fill="var(--glyph-shadow)" />
          <g className="glyph-paper">
            <path d="M20 8h18l12 12v29a5 5 0 0 1-5 5H20a5 5 0 0 1-5-5V13a5 5 0 0 1 5-5Z" fill={body} stroke="var(--glyph-edge)" />
            <path d="M38 8v9a3 3 0 0 0 3 3h9" fill={light} stroke="var(--glyph-edge)" strokeLinejoin="round" />
            <path d="M23 29h18M23 35h18M23 41h11" stroke="var(--glyph-ink)" strokeWidth="2.5" strokeLinecap="round" />
            <rect className="glyph-detail-light" x="22" y="46" width="9" height="2" rx="1" fill="var(--glyph-shine)" />
          </g>
        </>}
        {kind === 'scan' && <>
          <rect x="18" y="17" width="28" height="32" rx="5" fill={body} stroke="var(--glyph-edge)" />
          <path d="M24 26h16M24 33h11M24 40h15" stroke="var(--glyph-ink)" strokeWidth="2.2" strokeLinecap="round" />
          <g className="glyph-scan-corners" stroke="var(--glyph-shine)" strokeWidth="2.5" strokeLinecap="round">
            <path d="M12 23v-8a3 3 0 0 1 3-3h8M41 12h8a3 3 0 0 1 3 3v8M52 41v8a3 3 0 0 1-3 3h-8M23 52h-8a3 3 0 0 1-3-3v-8" />
          </g>
          <g clipPath={`url(#${id}-scan)`}><g className="glyph-scan-light">
            <rect x="18" y="18" width="28" height="10" fill="var(--glyph-shine)" opacity=".24" />
            <path d="M18 28h28" stroke="var(--glyph-shine)" strokeWidth="1.5" />
          </g></g>
        </>}
        {kind === 'clock' && <>
          <circle cx="32" cy="35" r="24" fill="var(--glyph-shadow)" />
          <circle cx="32" cy="31" r="24" fill={body} stroke="var(--glyph-edge)" strokeWidth="1.2" />
          <circle cx="32" cy="31" r="18" fill={light} fillOpacity=".3" stroke="var(--glyph-ink)" strokeOpacity=".2" />
          <path d="M32 15v2M48 31h-2M32 47v-2M16 31h2" stroke="var(--glyph-ink)" strokeWidth="2" strokeLinecap="round" />
          <path d="m32 31 8 5" stroke="var(--glyph-ink)" strokeWidth="3" strokeLinecap="round" />
          <g className="glyph-clock-hand">
            <path d="M32 31V20" stroke="var(--glyph-shine)" strokeWidth="3" strokeLinecap="round" />
          </g>
          <circle cx="32" cy="31" r="2.5" fill="var(--glyph-ink)" />
          <path d="M17 17a21 21 0 0 1 13-6" stroke="var(--glyph-shine)" strokeOpacity=".7" strokeLinecap="round" />
        </>}
      </svg>
    </span>
  )
}
