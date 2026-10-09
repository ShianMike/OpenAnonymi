import { SlidersHorizontal, ChevronDown } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import { DetectionControls } from '../detection/DetectionControls'
import type { ReviewController } from './useReviewController'
import { ReviewRules } from '../rules/ReviewRules'
import '../rules/rules.css'
import { extras } from '../detection/categories'
import { phoneRegions } from '../ui/phoneRegions'

export function ReviewSettings({ review, csrf }: { review: ReviewController; csrf: string }) {
  if (review.state.kind !== 'ready') return null
  const disabled = review.actionPending
  const categories = [...(review.emailEnabled ? ['email' as const] : []), ...(review.phoneEnabled ? ['phone' as const] : []), ...review.extraCategories]
  return (
    <details className="review-settings" id="review-suggestion-settings">
      <summary>
        <span>
          <SlidersHorizontal size={18} strokeWidth={1.6} aria-hidden="true" />
          <strong>What to look for</strong><small className="review-settings-count">{categories.length}</small>
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </summary>
      <div className="review-settings-body">
        <p>Change these only if you need to. Saving resets suggestions and confirmation; check the text again afterward.</p>
        <div className="review-setting-choices">
          <DetectionControls prefix="review" variant="checkbox" disabled={disabled}
            disabledReason="Wait for the current review changes to finish saving."
            categories={categories}
            onChange={(categories) => {
              review.setEmailEnabled(categories.includes('email'))
              review.setPhoneEnabled(categories.includes('phone'))
              review.setExtraCategories(extras(categories))
              review.setConfirmedPreview(false)
              review.setPreparedDownload(null)
            }} />
        </div>
        <div className="review-settings-footer">
          <div>
            <label className="field-label" htmlFor="scan-phone-region">
              {review.extraCategories.includes('date') ? 'Phone and date region' : 'Phone region'}
            </label>
            <GlassSelect
              id="scan-phone-region"
              value={review.phoneRegion}
              disabled={disabled}
              onValueChange={(value) => {
                review.setPhoneRegion(value)
                review.setConfirmedPreview(false)
                review.setPreparedDownload(null)
              }}
            >
              {phoneRegions.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </GlassSelect>
          </div>
          <button
            type="button"
            className="button-primary"
            onClick={() => void review.saveSettings()}
            disabled={!review.settingsDirty || review.dirty || disabled || review.conflict}
          >
            {review.settingsPending ? 'Saving settings…' : 'Save suggestion settings'}
          </button>
        </div>
        <details className="review-advanced-rules"><summary>Advanced workspace rules <ChevronDown size={14} aria-hidden="true" /></summary><ReviewRules review={review} csrf={csrf} /></details>
      </div>
    </details>
  )
}
