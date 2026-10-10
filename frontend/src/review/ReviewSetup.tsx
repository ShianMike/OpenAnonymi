import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { detectionChoices, languageName } from '../detection/categories'
import { phoneRegions } from '../ui/phoneRegions'
import { useState } from 'react'
import { RetentionDialog } from '../retention/RetentionDialog'

export function ReviewSetup({ review }: { review: ReviewController }) {
  const [renewing, setRenewing] = useState<HTMLButtonElement | null>(null)
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  const choices = detectionChoices.filter((choice) => saved.categories.includes(choice.category))
  return (
    <details className="review-details review-setup">
      <summary>
        <SlidersHorizontal size={16} aria-hidden="true" />
        <span>Saved options<small>Language, phone region, and retention</small></span>
        <ChevronDown size={14} aria-hidden="true" />
      </summary>
      <dl className="review-setup-facts">
        <div><dt>Look for</dt><dd>{choices.map((choice) => choice.label).join(', ') || 'None'}</dd></div>
        <div><dt>Phone region</dt><dd>{phoneRegions.find(([code]) => code === saved.phone_region)?.[1] ?? saved.phone_region}</dd></div>
        <div><dt>Names and places</dt><dd>{languageName(saved.language)} text</dd></div>
        <div><dt>Available until</dt><dd><time dateTime={saved.expires_at} title={new Date(saved.expires_at).toLocaleString()}>{new Date(saved.expires_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}, {new Date(saved.expires_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time></dd></div>
      </dl>
      {review.canEdit && <button type="button" disabled={review.actionPending || review.dirty || review.settingsDirty || review.conflict}
        onClick={event => setRenewing(event.currentTarget)}>Renew retention</button>}
      {renewing && <RetentionDialog key={`${saved.version.document_id}.${review.retentionCsrf}`} documentId={saved.version.document_id} csrf={review.retentionCsrf} returnFocus={renewing}
        onClose={() => setRenewing(null)} onSaved={value => { review.retentionRenewed(saved.version.document_id, value.expires_at); setRenewing(null) }} />}
      {saved.preset_id && <p>This review uses a copy of your saved settings. Later changes to those settings won’t change this review.</p>}
      {saved.preset_id && review.canEdit && <>
        <p>Using the latest replacement defaults keeps your saved decisions and suggestion settings. You will need to confirm the output again.</p>
        <button type="button" disabled={review.actionPending || review.dirty || review.settingsDirty || review.conflict}
          onClick={() => void review.useLatestDefaults()}>Use the latest preset defaults</button>
      </>}
    </details>
  )
}
