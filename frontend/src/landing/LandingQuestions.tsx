import { ArrowRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PrivacyGlyph } from './PrivacyGlyph'

const questions = [
  { title: 'What can I bring into a review?', answer: 'Paste text or import one TXT, PDF, or Word DOCX document. PDF and DOCX imports give you an extracted-text preview first. Scanned PDFs need OCR elsewhere, and encrypted PDFs aren’t supported. The reviewed download is a TXT file.' },
  { title: 'Does it automatically make my document anonymous?', answer: 'No. Suggestions are a starting point and can miss or misclassify details. You decide each finding, mark anything else that matters, and read the full output before confirming. Context can still identify someone.' },
  { title: 'What is the difference between Label, Redact, and Keep?', answer: 'Label replaces a detail with a reusable label such as PERSON_001. Redact replaces it with [REDACTED]. Keep leaves it as written and asks for your reason. You can change a decision before confirming your reviewed version.' },
  { title: 'Can I review with a teammate?', answer: 'A document owner can assign a workspace teammate to that review. The assigned member can decide findings, discuss details, and approve the exact version after the owner confirms it. Source edits and exports stay with the owner. You can also require this second approval before exporting.' },
  { title: 'Can I pick up a review later?', answer: 'Yes. Workspace → Continue review brings together your last accessible document, assigned reviews, and unfinished reviews you own. On this device, it remembers your view and reading position. An expired or inaccessible document cannot be reopened.' },
]

export function LandingQuestions({ signedIn }: { signedIn: boolean }) {
  return (
    <>
      <section id="questions" className="landing-questions landing-container" aria-labelledby="questions-title">
        <div className="landing-section-heading" data-landing-reveal><span className="landing-eyebrow">Before you begin.</span><h2 id="questions-title">A few good questions.</h2><p>A clearer picture of what a review can do.</p></div>
        <div className="landing-faq-list" data-landing-reveal>{questions.map(({ title, answer }) => <details key={title}><summary>{title}<Plus size={18} aria-hidden="true" /></summary><p>{answer}</p></details>)}</div>
      </section>
      <section className="landing-final landing-glass landing-container" aria-labelledby="landing-final-title" data-landing-reveal>
        <div className="landing-final-glyph"><PrivacyGlyph kind="shield" size={64} /></div>
        <span className="landing-eyebrow">Let the useful part travel.</span>
        <h2 id="landing-final-title">Your next story.<br /><span>A little more private.</span></h2>
        <Link className="landing-button" to={signedIn ? '/new' : '/sign-up'}>{signedIn ? 'Start a new review' : 'Create your workspace'}<ArrowRight size={18} aria-hidden="true" /></Link>
        <p>Bring your words. Decide what leaves the page.</p>
      </section>
    </>
  )
}
