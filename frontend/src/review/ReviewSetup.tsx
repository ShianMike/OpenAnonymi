import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { languageName } from '../detection/categories'
import { categoryPresentation } from '../rules/categoryPresentation'

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
        <div><dt>Suggestions</dt><dd>{saved.categories.map((category) => categoryPresentation[category].label).join(', ') || 'None'}</dd></div>
        <div><dt>Phone region</dt><dd>{saved.phone_region}</dd></div>
        <div><dt>Name and place language</dt><dd>{languageName(saved.language)}</dd></div>
        <div><dt>Expires</dt><dd>{new Date(saved.expires_at).toLocaleString()}</dd></div>
      </dl>
      {saved.preset_id && <p>Started with a Rules preset. Preferred action: {saved.preferred_action}. Later preset changes do not update this review.</p>}
      {saved.preset_id && review.canEdit && <>
        <p>Using the latest replacement defaults keeps your saved decisions and suggestion settings. You will need to confirm the output again.</p>
        <button type="button" disabled={review.actionPending || review.dirty || review.settingsDirty || review.conflict}
          onClick={() => void review.useLatestDefaults()}>Use the latest preset defaults</button>
      </>}
    </details>
  )
}
