import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import type { ReviewController } from './useReviewController'

export function ReviewSetup({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  return (
    <details className="review-details review-setup">
      <summary>
        <SlidersHorizontal size={14} aria-hidden="true" /> Review setup
        <ChevronDown size={14} aria-hidden="true" />
      </summary>
      <dl className="review-setup-facts">
        <div><dt>Suggestions</dt><dd>{saved.categories.map((category) => category[0].toUpperCase() + category.slice(1)).join(', ') || 'None'}</dd></div>
        <div><dt>Phone region</dt><dd>{saved.phone_region}</dd></div>
        <div><dt>Expires</dt><dd>{new Date(saved.expires_at).toLocaleString()}</dd></div>
      </dl>
      {saved.preset_id && <p>Started with a Rules preset. Preferred action: {saved.preferred_action}. Later preset changes do not update this review.</p>}
    </details>
  )
}
