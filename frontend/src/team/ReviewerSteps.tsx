import { Check, UserRoundCheck } from 'lucide-react'
import type { ReviewController } from '../review/useReviewController'
import './reviewer-flow.css'

export function ReviewerSteps({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready' || review.canEdit) return null
  const confirmed = ['ready', 'exported'].includes(review.state.saved.status)
  const approved = Boolean(review.handoff.value?.approved_at)
  const active = review.pendingFindings.length ? 0 : confirmed ? 2 : 1
  return <div className="reviewer-flow" aria-label="Assigned review workflow">
    <div className="reviewer-flow-copy">
      <UserRoundCheck size={19} aria-hidden="true" />
      <div><strong>You’re the assigned reviewer</strong><p>Decide findings and discuss details. The owner handles source edits and exports.</p></div>
    </div>
    <ol>
      {['Decide findings', 'Owner confirms', 'Your approval'].map((label, index) => (
        <li key={label} data-state={approved || index < active ? 'done' : index === active ? 'current' : 'later'}
          aria-current={!approved && index === active ? 'step' : undefined}>
          <span aria-hidden="true">{approved || index < active ? <Check size={12} /> : index + 1}</span>{label}
        </li>
      ))}
    </ol>
  </div>
}
