import type { CSSProperties } from 'react'
import {
  ArrowRight, AtSign, Building2, CalendarDays, Check, Hash, House, IdCard, Image, KeyRound, Link2,
  MapPin, MessageSquare, Minus, Phone, Layers, Tag, UserRound, type LucideIcon,
} from 'lucide-react'
import './story.css'

const decisions: { action: 'label' | 'redact' | 'keep'; Icon: LucideIcon; name: string; from: string; to: string }[] = [
  { action: 'label', Icon: Tag, name: 'Replace', from: 'research.participant@example.test', to: 'EMAIL_001' },
  { action: 'redact', Icon: Minus, name: 'Hide', from: '+1 202-555-0147', to: '[REDACTED]' },
  { action: 'keep', Icon: Check, name: 'Keep', from: '14 October 2026', to: '14 October 2026' },
]

const detectable = [
  { Icon: UserRound, label: 'People' }, { Icon: AtSign, label: 'Emails' }, { Icon: Phone, label: 'Phone numbers' },
  { Icon: House, label: 'Addresses' }, { Icon: Building2, label: 'Organizations' }, { Icon: MapPin, label: 'Places' },
  { Icon: CalendarDays, label: 'Dates' }, { Icon: Link2, label: 'Web addresses' }, { Icon: Hash, label: 'Identifiers' },
  { Icon: IdCard, label: 'National IDs' }, { Icon: KeyRound, label: 'Secrets' },
]

const tracks = [
  { name: 'On your own', steps: ['Decide', 'Read', 'Confirm and export'] },
  { name: 'With a teammate', steps: ['Decide', 'Owner confirms', 'Reviewer approves'] },
]

const delay = (index: number) => ({ '--reveal-delay': index }) as CSSProperties

/** Lets an email wrap after its @ on narrow screens instead of mid-word. */
function Breakable({ text }: { text: string }) {
  const at = text.indexOf('@')
  return at < 0 ? text : <>{text.slice(0, at + 1)}<wbr />{text.slice(at + 1)}</>
}

export function WorkflowStory() {
  return (
    <>
      <section id="features" className="landing-section landing-features" aria-labelledby="features-title">
        <div className="landing-container">
          <header className="landing-section-head" data-landing-reveal>
            <h2 id="features-title">Privacy in the details.</h2>
            <p>Suggestions do the searching. You make every call.</p>
          </header>
          <div className="landing-bento">
            <article id="how-it-works" className="bento-cell bento-decide" data-landing-reveal>
              <h3>Decide what stays.</h3>
              <p>Use a category label or another replacement style, hide the value, or keep it with a reason. Add any details the scan misses.</p>
              <ul className="bento-art decide-rows" aria-label="Example decisions">
                {decisions.map(({ action, Icon, name, from, to }) => <li className="decide-row" key={action} data-action={action}>
                  <span className="decide-action"><Icon size={15} aria-hidden="true" />{name}</span>
                  <span className="decide-from"><Breakable text={from} /></span>
                  <ArrowRight className="decide-arrow" size={15} aria-hidden="true" />
                  <span className="decide-to"><span className="landing-out" data-action={action}>{to}</span>
                    {action === 'keep' && <span className="decide-reason">with a reason</span>}</span>
                </li>)}
              </ul>
            </article>
            <article className="bento-cell bento-detect" data-landing-reveal style={delay(1)}>
              <h3>Built-in detection.</h3>
              <p>Choose what to look for, from names and emails to IDs and secrets. Add anything it misses.</p>
              <ul className="bento-art detect-chips" aria-label="Detail types">
                {detectable.map(({ Icon, label }) => <li key={label}><Icon size={14} aria-hidden="true" />{label}</li>)}
              </ul>
            </article>
            <article className="bento-cell bento-scan" data-landing-reveal>
              <h3>Scans and PDFs, too.</h3>
              <p>Review findings on the page and keep its appearance in the PDF export. Redactions are flattened into page images, without the original text layer.</p>
              <div className="bento-art scan-art" aria-hidden="true">
                <div className="scan-page scan-page-source"><Image size={16} /><i /><i /><i /><i /><i /></div>
                <ArrowRight className="scan-arrow" size={16} />
                <div className="scan-page scan-page-text"><Layers size={16} /><i /><i /><i className="is-found" /><i /><i /></div>
              </div>
            </article>
            <article className="bento-cell bento-team" data-landing-reveal style={delay(1)}>
              <h3>A second pair of eyes.</h3>
              <p>Assign a workspace teammate to review findings and discuss decisions. Require their approval of the exact version before you export.</p>
              <div className="bento-art team-tracks">
                {tracks.map(({ name, steps: trackSteps }) => <div className="team-track" key={name}>
                  <h4>{name}</h4>
                  <ol>{trackSteps.map((text, index) => <li key={text} data-done={index === 0}>
                    {index === 0 && <Check size={14} strokeWidth={2.4} aria-hidden="true" />}{text}
                  </li>)}</ol>
                </div>)}
                <p className="team-note"><MessageSquare size={14} aria-hidden="true" />Protected comments. Only the owner exports.</p>
              </div>
            </article>
          </div>
        </div>
      </section>
    </>
  )
}
