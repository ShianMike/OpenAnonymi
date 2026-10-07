import type { ReactNode } from 'react'
import { Brand } from '../ui/Brand'
import './entrance.css'

export function EntranceFrame({ children, eyebrow = 'A moment of care' }: { children: ReactNode; eyebrow?: string }) {
  return <main id="main-content" className="loading-screen">
    <header className="loading-screen-brand"><Brand /><span className="loading-screen-tagline">A little more private.</span></header>
    <div className="loading-screen-center">
      <span className="loading-screen-eyebrow">{eyebrow}</span>
      {children}
    </div>
    <p className="loading-screen-footnote">Your review. Your call.</p>
  </main>
}
