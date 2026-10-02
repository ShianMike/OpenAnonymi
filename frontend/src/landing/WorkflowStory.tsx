import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowUpRight, Check } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '../ui/cn'
import { PrivacyOrbit } from './PrivacyOrbit'
import { PrivacyGlyph, type PrivacyGlyphKind } from './PrivacyGlyph'
import './story.css'

const steps: { number: string; icon: PrivacyGlyphKind; title: string; text: string; tag: string }[] = [
  { number: '01', icon: 'document', title: 'Bring your words.', text: 'Paste a note or import a TXT, PDF, or Word document. Preview the extracted text before you start.', tag: 'A clear starting point' },
  { number: '02', icon: 'scan', title: 'Give the details a thought.', text: 'Local suggestions help you find possible personal details. Label, redact, or keep each one. Mark anything else yourself.', tag: 'A human decision, every time' },
  { number: '03', icon: 'shield', title: 'Share with a little more care.', text: 'Read the full reviewed output, confirm the version, then copy it or download a TXT. The useful story stays with you.', tag: 'A final look before it leaves' },
]

export function WorkflowStory({ signedIn }: { signedIn: boolean }) {
  const [teamMode, setTeamMode] = useState('solo')
  return (
    <>
      <section id="how-it-works" className="landing-process landing-container" aria-labelledby="process-title">
        <div className="landing-section-heading" data-landing-reveal>
          <span className="landing-eyebrow">A small pause. A thoughtful process.</span>
          <h2 id="process-title">Keep what matters.<br /><span>Consider what identifies.</span></h2>
          <p>From a rough note to a considered version, with you in control of every change.</p>
        </div>
        <div className="landing-process-steps">
          {steps.map(({ number, icon, title, text, tag }) => <article className="landing-process-step" key={number} data-landing-reveal>
            <div className="landing-step-top"><span>{number}</span><PrivacyGlyph kind={icon} size={46} /></div>
            <h3>{title}</h3><p>{text}</p><small><Check size={14} aria-hidden="true" /> {tag}</small>
          </article>)}
        </div>
      </section>
      <section className="landing-care landing-container" aria-labelledby="care-title">
        <div className="landing-care-art landing-glass" data-landing-reveal><PrivacyOrbit /></div>
        <div className="landing-care-copy" data-landing-reveal>
          <span className="landing-eyebrow">Tools that make room for your judgment.</span>
          <h2 id="care-title">Helpful suggestions.<br /><span>The last word is yours.</span></h2>
          <p>Names, contact details, places, and your team’s own phrases can all tell a story. Review the context as well as the highlighted details.</p>
          <ul className="landing-care-points">
            <li><PrivacyGlyph kind="scan" size={32} /><span><strong>Suggestions run locally</strong><small>Source text isn’t sent to an external model service.</small></span></li>
            <li><PrivacyGlyph kind="shield" size={32} /><span><strong>Protected drafts, a considered output</strong><small>Saved content is encrypted, with a fixed expiry for each review.</small></span></li>
            <li><PrivacyGlyph kind="keyboard" size={32} /><span><strong>A rhythm that works for you</strong><small>Optional keyboard review, without leaving your reading flow.</small></span></li>
          </ul>
          <p className="landing-care-note">Suggestions can miss details. A review helps you reduce exposure; it doesn’t guarantee anonymity.</p>
        </div>
      </section>
      <section className="landing-together landing-container" aria-labelledby="together-title" data-landing-reveal>
        <div className="landing-together-copy">
          <span className="landing-eyebrow">At your pace. In good company.</span>
          <h2 id="together-title">A little care.<br /><span>Another set of eyes.</span></h2>
          <p>Review on your own, or invite a workspace teammate into a specific document. Come back to your reading position, decisions, and discussion.</p>
          <Link className="landing-inline-link" to={signedIn ? '/continue' : '/sign-in?next=%2Fcontinue'}>Continue a review <ArrowUpRight size={17} aria-hidden="true" /></Link>
        </div>
        <Tabs.Root className="landing-team-demo landing-glass" value={teamMode} onValueChange={setTeamMode}>
          <Tabs.List aria-label="Review workflow"><Tabs.Trigger value="solo">On your own</Tabs.Trigger><Tabs.Trigger value="team"><PrivacyGlyph kind="people" size={23} /> With a teammate</Tabs.Trigger></Tabs.List>
          <div className="landing-team-content">
          {['solo', 'team'].map((mode) => <Tabs.Content forceMount key={mode} value={mode} aria-hidden={mode !== teamMode} inert={mode !== teamMode}>
            <div className="landing-team-document"><PrivacyGlyph kind="document" size={31} /><div><strong>Interview recap</strong><small>Example workflow</small></div><span className="landing-team-avatar">{mode === 'team' ? <PrivacyGlyph kind="people" size={30} /> : 'You'}</span></div>
            <ol className="landing-team-steps">
              {(mode === 'team' ? ['Decide findings together', 'Owner confirms the output', 'Reviewer approves that version'] : ['Make your decisions', 'Read the full reviewed output', 'Confirm, then copy or download']).map((text, index) => <li key={text}><span className={cn('landing-team-step-number', index === 0 && 'is-current')}>{index === 0 ? <Check size={14} aria-hidden="true" /> : index + 1}</span>{text}</li>)}
            </ol>
            <div className="landing-team-note"><PrivacyGlyph kind="message" size={25} />{mode === 'team' ? 'Protected comments stay with the assigned review.' : 'Pause whenever you need. Continue where you left off.'}</div>
          </Tabs.Content>)}
          </div>
        </Tabs.Root>
      </section>
    </>
  )
}
