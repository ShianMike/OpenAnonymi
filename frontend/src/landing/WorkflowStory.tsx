import { useState, type CSSProperties } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowUpRight, Check, Clock3, FileText, Image, LockKeyhole, MessageSquare, Minus, ScanText, Table2, Tag } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '../ui/cn'
import './story.css'

const steps = [
  { number: '01', Icon: FileText, title: 'Import', text: 'Text or files' },
  { number: '02', Icon: ScanText, title: 'Review', text: 'Your decisions' },
  { number: '03', Icon: Check, title: 'Share', text: 'Confirm & export' },
]

const formats = [
  { name: 'TXT', Icon: FileText }, { name: 'PDF', Icon: FileText },
  { name: 'DOCX', Icon: FileText }, { name: 'CSV', Icon: Table2 },
  { name: 'MD', Icon: FileText }, { name: 'IMAGE', Icon: Image },
]

export function WorkflowStory({ signedIn }: { signedIn: boolean }) {
  const [teamMode, setTeamMode] = useState('solo')
  return (
    <>
      <section id="how-it-works" className="landing-process landing-container" aria-labelledby="process-title">
        <h2 id="process-title" className="sr-only">From draft to share</h2>
        <div className="landing-process-steps">
          {steps.map(({ number, Icon, title, text }) => <article className="landing-process-step" key={number} data-landing-reveal>
            <div className="landing-step-top"><Icon size={24} strokeWidth={1.5} aria-hidden="true" /></div>
            <h3>{title}</h3><p>{text}</p>
          </article>)}
        </div>
      </section>
      <section className="landing-care landing-container" aria-labelledby="care-title">
        <div className="landing-section-heading" data-landing-reveal><h2 id="care-title">Privacy in the details.</h2></div>
        <div className="landing-bento-grid">
          <article className="landing-feature landing-feature-decisions" data-landing-reveal>
            <div className="bento-findings" aria-hidden="true">
              <div className="privacy-ticket privacy-ticket-label"><Tag size={23} strokeWidth={1.5} /><small>Label</small><span>Maya Chen</span><strong>PERSON_001</strong></div>
              <div className="privacy-ticket privacy-ticket-redact"><Minus size={23} strokeWidth={1.5} /><small>Redact</small><div className="privacy-redaction-bars"><i /><i /></div><strong>[REDACTED]</strong></div>
              <div className="privacy-ticket privacy-ticket-keep"><Check size={23} strokeWidth={1.5} /><small>Keep</small><div className="privacy-note-lines"><i /><i /></div><strong>Useful feedback</strong></div>
            </div>
            <h3>Decide what stays.</h3>
            <span className="sr-only">Label a detail, redact it, or keep it. You can also mark details manually.</span>
          </article>
          <article className="landing-feature landing-feature-protection" data-landing-reveal>
            <div className="landing-care-art" aria-hidden="true"><div className="privacy-vault"><LockKeyhole size={48} strokeWidth={1.2} /><div className="privacy-note-lines"><i /><i /><i /></div></div></div>
            <h3>Encrypted drafts.</h3><span className="landing-expiry"><Clock3 size={14} aria-hidden="true" /> Automatic expiry</span>
          </article>
          <article className="landing-feature landing-feature-imports" data-landing-reveal>
            <div className="bento-files" aria-hidden="true">{formats.map(({ name, Icon }, index) => <span key={name} style={{ '--file-order': index } as CSSProperties}><Icon size={28} strokeWidth={1.2} /><strong>{name}</strong><div className="privacy-note-lines"><i /><i /></div></span>)}</div>
            <h3>Bring your draft.</h3><small className="landing-format-list">TXT · PDF · DOCX · CSV · MD · Images</small>
          </article>
          <article className="landing-feature landing-together" aria-labelledby="together-title" data-landing-reveal>
            <div className="landing-together-copy"><h3 id="together-title">A second pair<br />of eyes.</h3><Link className="landing-inline-link" to={signedIn ? '/continue' : '/sign-in?next=%2Fcontinue'}>Continue review <ArrowUpRight size={16} aria-hidden="true" /></Link></div>
            <Tabs.Root className="landing-team-demo" value={teamMode} onValueChange={setTeamMode}>
              <Tabs.List aria-label="Review workflow"><Tabs.Trigger value="solo">On your own</Tabs.Trigger><Tabs.Trigger value="team">With a teammate</Tabs.Trigger></Tabs.List>
              <div className="landing-team-content">
                {['solo', 'team'].map((mode) => <Tabs.Content forceMount key={mode} value={mode} aria-hidden={mode !== teamMode} inert={mode !== teamMode}>
                  <ol className="landing-team-steps">{(mode === 'team' ? ['Decide', 'Owner confirms', 'Reviewer approves'] : ['Decide', 'Read', 'Confirm & export']).map((text, index) => <li key={text}><span className={cn('landing-team-step-number', index === 0 && 'is-current')}>{index === 0 ? <Check size={18} aria-hidden="true" /> : index + 1}</span>{text}</li>)}</ol>
                  <div className="landing-team-note"><MessageSquare size={14} aria-hidden="true" />{mode === 'team' ? 'Protected comments · Owner exports' : 'Save now. Return later.'}</div>
                </Tabs.Content>)}
              </div>
            </Tabs.Root>
          </article>
        </div>
        <p className="landing-care-note">Suggestions can miss details. Review before sharing.</p>
      </section>
    </>
  )
}
