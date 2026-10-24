import type { CSSProperties } from 'react'
import { ArrowRight, ArrowUpRight, CodeXml, Hourglass, Info, LockKeyhole, ServerCog } from 'lucide-react'
import { Link } from 'react-router-dom'
import { sourceUrl } from './links'

// Each statement mirrors the published Privacy Notice and README. Keep them in step.
const points = [
  { Icon: ServerCog, title: 'No outside AI services', text: 'Detection and OCR run on the service itself. Your documents aren’t sent to an external AI provider.' },
  { Icon: LockKeyhole, title: 'Encrypted at rest', text: 'Stored documents and working drafts are encrypted, with keys kept outside the database.' },
  { Icon: Hourglass, title: 'Reviews expire', text: 'Workspace admins choose how long new review content is kept, from 1 to 30 days.' },
  { Icon: CodeXml, title: 'Open source', text: 'The code is public under AGPL-3.0. Inspect how it works, or host your own copy.' },
]

export function LandingSecurity() {
  return (
    <section id="security" className="landing-section landing-security" aria-labelledby="security-title">
      <div className="landing-container">
        <header className="landing-section-head" data-landing-reveal>
          <h2 id="security-title">Handled with care.</h2>
          <p>What the hosted service does with the text you bring.</p>
        </header>
        <ul className="security-grid">
          {points.map(({ Icon, title, text }, index) => <li className="security-item" key={title} data-landing-reveal
            style={{ '--reveal-delay': index % 2 } as CSSProperties}>
            <span className="security-icon"><Icon size={20} strokeWidth={1.75} aria-hidden="true" /></span>
            <h3>{title}</h3>
            <p>{text}</p>
            {title === 'Open source' && <a className="landing-text-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">
              View the source<span className="sr-only"> (opens in a new tab)</span><ArrowUpRight size={15} aria-hidden="true" /></a>}
          </li>)}
        </ul>
        <div className="security-note" data-landing-reveal>
          <p><Info size={17} aria-hidden="true" />Suggestions can miss details. Read the whole output before you share it.</p>
          <Link className="landing-text-link" to="/privacy">Read the Privacy Notice <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
      </div>
    </section>
  )
}
