import type { CSSProperties, ReactNode, Ref } from 'react'
import { Check, Fingerprint } from 'lucide-react'
import { useAppearance } from '../appearance/useAppearance'
import type { BootTone } from './bootScreen'

/** The full-screen frame index.html paints first. Keep the two in step; public/startup.css styles both. */
export function BootFrame({ tone, children, frameRef, entrance = true, slow = false, style }: {
  tone?: BootTone; children: ReactNode; frameRef?: Ref<HTMLDivElement>; entrance?: boolean; slow?: boolean; style?: CSSProperties
}) {
  const { theme } = useAppearance()
  return <div ref={frameRef} className="boot-screen" data-tone={tone ?? theme} data-entrance={entrance ? undefined : 'skip'}
    data-slow={slow || undefined} style={style}>
    <header className="boot-bar">
      <span className="boot-brand">
        <span className="boot-brand-mark"><Fingerprint strokeWidth={1.6} aria-hidden="true" /></span>
        <span className="boot-wordmark">OpenAnonymi</span>
      </span>
    </header>
    <main id="main-content" className="boot-main">{children}</main>
    <p className="boot-note">Your review. Your call.</p>
  </div>
}

/** A note being reviewed: a scan passes, details are labeled and redacted, and the note is confirmed. */
export function BootArt() {
  return <div className="boot-art" aria-hidden="true">
    <div className="boot-doc">
      <div className="boot-doc-head"><i className="boot-doc-title" /><span className="boot-check"><Check strokeWidth={3} /></span></div>
      <div className="boot-doc-body">
        <span className="boot-row"><i /><i className="boot-find boot-find-1" /><i /></span>
        <span className="boot-row"><i /><i className="boot-find boot-find-2" /><i /></span>
        <span className="boot-row"><i /><i /></span>
        <span className="boot-row"><i className="boot-find boot-find-3" /><i /></span>
        <span className="boot-scan" />
      </div>
    </div>
  </div>
}
