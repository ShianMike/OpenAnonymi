import { useId, type CSSProperties } from 'react'
import { cn } from '../ui/cn'
import './glyph.css'

export type PrivacyGlyphKind = 'document' | 'scan' | 'shield' | 'fingerprint' | 'people' | 'message' | 'keyboard'

/** Original miniature illustrations, with motion carried by separate SVG layers. */
export function PrivacyGlyph({ kind, size = 36, className }: {
  kind: PrivacyGlyphKind; size?: number; className?: string
}) {
  const id = useId()
  const body = `url(#${id}-body)`
  const light = `url(#${id}-light)`
  return (
    <span className={cn('privacy-glyph', `privacy-glyph-${kind}`, 'landing-loop-scene', className)}
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
        {kind === 'shield' && <>
          <path d="M32 9 51 17v15c0 12-11 21-19 25-8-4-19-13-19-25V17L32 9Z" fill="var(--glyph-shadow)" />
          <path d="m32 6 18 8v15c0 12-10 20-18 24-8-4-18-12-18-24V14L32 6Z" fill={body} stroke="var(--glyph-edge)" strokeWidth="1.2" />
          <path d="m32 13 12 5v11c0 8-6 14-12 18-6-4-12-10-12-18V18l12-5Z" stroke="var(--glyph-ink)" strokeOpacity=".32" />
          <g className="glyph-shield-check"><circle cx="32" cy="29" r="10" fill="var(--glyph-ink)" opacity=".12" />
            <path d="m26 29 4 4 8-9" stroke="var(--glyph-shine)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </g>
          <path d="m23 15 7-3" stroke="var(--glyph-shine)" strokeOpacity=".65" strokeLinecap="round" />
        </>}
        {kind === 'fingerprint' && <>
          <circle cx="32" cy="32" r="27" fill={body} fillOpacity=".16" stroke="var(--glyph-edge)" strokeOpacity=".35" />
          <g stroke="var(--glyph-shine)" strokeWidth="1.8" strokeLinecap="round">
            <path className="glyph-fingerprint-outer" d="M13 28c0-12 8-20 19-20 9 0 17 5 20 13M12 35v5M51 29c2 8 0 16-3 23" />
            <path className="glyph-fingerprint-middle" d="M20 48c2-6 2-12 2-19 0-6 4-10 10-10s10 4 10 10M42 35c0 6-1 11-3 18M19 20c3-6 8-9 14-9" />
            <path className="glyph-fingerprint-inner" d="M27 54c3-9 3-18 3-26 0-2 1-3 3-3s3 1 3 3v14M33 48l-1 6" />
          </g>
          <circle className="glyph-fingerprint-spark" cx="49" cy="17" r="2.5" fill="var(--glyph-shine)" />
        </>}
        {kind === 'people' && <>
          <g className="glyph-person-back"><circle cx="42" cy="22" r="8" fill={light} opacity=".8" />
            <path d="M31 47v-3c0-8 4-13 11-13s12 5 12 13v3" fill={body} stroke="var(--glyph-edge)" />
          </g>
          <g className="glyph-person-front"><circle cx="24" cy="23" r="9" fill={body} stroke="var(--glyph-edge)" />
            <path d="M10 49v-4c0-8 5-13 14-13s14 5 14 13v4" fill={body} stroke="var(--glyph-edge)" />
            <path d="M17 39c2-2 4-3 7-3" stroke="var(--glyph-shine)" strokeOpacity=".7" strokeLinecap="round" />
          </g>
          <circle className="glyph-detail-light" cx="47" cy="47" r="7" fill="var(--glyph-mid)" />
          <path d="m44 47 2 2 4-4" stroke="var(--glyph-ink)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </>}
        {kind === 'message' && <>
          <path d="M15 14h34a6 6 0 0 1 6 6v23a6 6 0 0 1-6 6H28l-13 9v-9a6 6 0 0 1-6-6V20a6 6 0 0 1 6-6Z" fill="var(--glyph-shadow)" />
          <path d="M16 9h32a6 6 0 0 1 6 6v23a6 6 0 0 1-6 6H28l-12 8v-8a6 6 0 0 1-6-6V15a6 6 0 0 1 6-6Z" fill={body} stroke="var(--glyph-edge)" />
          <g fill="var(--glyph-shine)"><circle className="glyph-message-dot" cx="23" cy="27" r="2.6" /><circle className="glyph-message-dot" cx="32" cy="27" r="2.6" /><circle className="glyph-message-dot" cx="41" cy="27" r="2.6" /></g>
        </>}
        {kind === 'keyboard' && <>
          <rect x="7" y="20" width="50" height="32" rx="7" fill="var(--glyph-shadow)" />
          <rect x="7" y="14" width="50" height="32" rx="7" fill={body} stroke="var(--glyph-edge)" />
          <g fill="var(--glyph-ink)" opacity=".8">
            {[16, 24, 32, 40, 48].map((x) => <rect key={x} x={x-2} y="22" width="4" height="4" rx="1" />)}
            {[16, 24, 32, 40].map((x) => <rect key={x} x={x-2} y="30" width="4" height="4" rx="1" />)}
            <rect className="glyph-key" x="45" y="30" width="6" height="10" rx="1.5" /><rect x="21" y="38" width="19" height="3" rx="1.5" />
          </g>
        </>}
      </svg>
    </span>
  )
}
