import { ArrowRight, Fingerprint, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

const questions = [
  { title: 'What can I import?', answer: 'TXT, Markdown, CSV, PDF, DOCX, and images. Scans use local English OCR; check extraction before saving. Encrypted PDFs aren’t supported. Confirmed outputs include TXT, Word, PDF, a redaction report, and reviewed CSV for CSV imports.' },
  { title: 'Will it make my document anonymous?', answer: 'No guarantee. Suggestions can miss or misclassify details, and context can identify someone. Make your decisions, add missed findings, and read the full output before confirming.' },
  { title: 'Label, Redact, or Keep?', answer: 'Label uses a reusable placeholder. Redact replaces the detail with [REDACTED]. Keep leaves it unchanged and requires a reason. Decisions can change until you confirm.' },
  { title: 'Can I review with a teammate?', answer: 'Owners can assign workspace teammates to decide findings, comment, and approve the exact version after owner confirmation. Source edits and exports stay with the owner. A second approval can be required before export.' },
  { title: 'Can I pick up a review later?', answer: 'Yes. Workspace → Continue review holds your unfinished and assigned reviews. Your view and position are remembered on this device. Expired or inaccessible reviews stay closed.' },
]

export function LandingQuestions({ signedIn }: { signedIn: boolean }) {
  return (
    <>
      <section id="questions" className="landing-questions landing-container" aria-labelledby="questions-title">
        <div className="landing-section-heading" data-landing-reveal><h2 id="questions-title">Good to know.</h2></div>
        <div className="landing-faq-list" data-landing-reveal>{questions.map(({ title, answer }) => <details key={title}><summary>{title}<Plus size={18} aria-hidden="true" /></summary><p>{answer}</p></details>)}</div>
      </section>
      <section className="landing-final landing-container" aria-labelledby="landing-final-title" data-landing-reveal>
        <div><h2 id="landing-final-title">Share on<br /><span>your terms.</span></h2><Link className="landing-button" to={signedIn ? '/new' : '/sign-up'}>Start a review<ArrowRight size={18} aria-hidden="true" /></Link></div>
        <Fingerprint className="landing-final-art" size={210} strokeWidth={.8} aria-hidden="true" />
      </section>
    </>
  )
}
