import { ArrowRight, CheckCircle2, Eye, UserRoundCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ReviewController } from '../review/useReviewController'
import { readReviewedOutput } from './reviewerNavigation'
import './reviewer-flow.css'

export function ReviewerCompletion({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  const confirmed = ['ready', 'exported'].includes(saved.status)
  const handoff = review.handoff.value
  const approved = Boolean(handoff?.approved_at)
  const remaining = review.pendingFindings.length
  const blocked = review.actionPending || review.conflict
  const title = approved ? 'You approved this version' : remaining ? 'Finish your finding decisions'
    : confirmed ? handoff ? 'Your approval is next' : 'Check the reviewed output' : 'Ready for the owner’s final check'
  return <section className="review-completion reviewer-completion" aria-labelledby="completion-heading">
    <div className="completion-heading">
      <span className="completion-icon"><UserRoundCheck size={21} strokeWidth={1.4} aria-hidden="true" /></span>
      <div><span className="review-eyebrow">YOUR REVIEW</span><h2 id="completion-heading">{title}</h2></div>
      {approved && <CheckCircle2 size={20} aria-hidden="true" />}
    </div>
    <p>{approved ? 'Your independent approval is saved for this exact version. The owner can handle sharing.'
      : remaining ? `${remaining} ${remaining === 1 ? 'finding still needs' : 'findings still need'} a decision. Then read the full output, including unmarked passages.`
      : confirmed ? handoff ? 'Read the full reviewed output, then use Assigned to you to approve this exact version. Context can still identify someone.' : 'Read the full reviewed output. Your approval status is being checked in Assigned to you.'
      : 'Your decisions are saved. Read the full output and discuss any concerns. The owner must confirm the version before you can approve it.'}</p>
    <div className="reviewer-actions">
      {remaining > 0 && <button className="button-primary" type="button" disabled={blocked} onClick={review.nextUnresolved}>
        Continue decisions <ArrowRight size={16} aria-hidden="true" />
      </button>}
      <button type="button" disabled={blocked} onClick={() => readReviewedOutput(review)}><Eye size={16} aria-hidden="true" /> Read reviewed output</button>
      {confirmed && !approved && handoff && !blocked && <a className="button-primary" href="#review-handoff">Go to approval <ArrowRight size={16} aria-hidden="true" /></a>}
      <Link to={`/continue?workspace=${saved.workspace_id}`}>Return to reviews</Link>
    </div>
    <p className="field-note">The owner confirms and exports. Your access covers reviewing, decisions, comments and independent approval.</p>
  </section>
}
