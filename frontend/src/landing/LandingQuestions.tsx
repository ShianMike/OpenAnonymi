import { ArrowRight, Fingerprint } from 'lucide-react'
import { Link } from 'react-router-dom'
import { supportEmail } from './links'

const questions = [
  { title: 'What can I import?', answer: 'Paste text or upload TXT, Markdown, PDF, DOCX, PNG, JPEG, TIFF, or WebP. Printed scans use English OCR on the service; compare the extraction with the original pages. Encrypted PDFs, CSV files and Excel workbooks aren’t supported.' },
  { title: 'Will my file keep its layout?', answer: 'TXT keeps spaces, tabs, and line endings. New PDF reviews preserve page sizes and appearance; reviewed PDF exports are flattened images without searchable text, forms, annotations, or attachments. Word preserves supported structure, but editing its text can simplify the layout. Images and Markdown are reviewed as extracted text.' },
  { title: 'Will it make my document anonymous?', answer: 'No guarantee. Suggestions can miss or misclassify details, and context can identify someone. Make your decisions, add missed findings, and read the full output before confirming.' },
  { title: 'What do Replace, Hide, and Keep do?', answer: 'Replace substitutes a category label or another available replacement style. Hide uses [REDACTED], or offers masks and date generalization where available; some options leave part of the detail visible. Keep leaves the detail unchanged and requires a reason. Your original stays intact; the reviewed output contains your decisions.' },
  { title: 'Can I review with a teammate?', answer: 'Owners can assign workspace teammates to decide findings, comment, and approve the exact version after owner confirmation. Source edits and exports stay with the owner. A second approval can be required before export.' },
  { title: 'Can I pick up a review later?', answer: 'Yes. Open Documents to find your drafts, reviews in progress, and completed reviews. Your view and position are remembered on this device. Review content is available only until its retention period ends and while you have access.' },
  { title: 'Does my document leave my browser?', answer: 'Yes. The service processes the content you submit. Detection and OCR run on that service, without sending document text to an external AI provider. Stored review content is encrypted. See the Privacy Notice for retention and access details.' },
]

export function LandingQuestions({ signedIn, startTo }: { signedIn: boolean; startTo: string }) {
  return (
    <>
      <section id="questions" className="landing-section landing-questions" aria-labelledby="questions-title">
        <div className="landing-container landing-faq">
          <header className="landing-faq-intro" data-landing-reveal>
            <h2 id="questions-title">Good to know.</h2>
            <p>Still wondering about something? Email <a className="landing-inline-link" href={`mailto:${supportEmail}`}>{supportEmail}</a>.</p>
          </header>
          <dl className="landing-faq-list" data-landing-reveal>
            {questions.map(({ title, answer }) => <div className="landing-faq-item" key={title}>
              <dt>{title}</dt>
              <dd>{answer}</dd>
            </div>)}
          </dl>
        </div>
      </section>
      <section className="landing-section landing-final" aria-labelledby="landing-final-title">
        <div className="landing-container">
          <div className="landing-cta" data-landing-reveal>
            <div className="landing-cta-copy">
              <h2 id="landing-final-title">Share on your terms.</h2>
              <p>Bring a draft, decide what stays, and share a version you’ve read.</p>
            </div>
            <div className="landing-cta-actions">
              <Link className="landing-button" to={startTo}>Start a review <ArrowRight size={17} aria-hidden="true" /></Link>
              <Link className="landing-button landing-button-secondary" to={signedIn ? '/documents' : '/sign-in'}>{signedIn ? 'Open documents' : 'Sign in'}</Link>
            </div>
            <Fingerprint className="landing-cta-art" strokeWidth={0.75} aria-hidden="true" />
          </div>
        </div>
      </section>
    </>
  )
}
