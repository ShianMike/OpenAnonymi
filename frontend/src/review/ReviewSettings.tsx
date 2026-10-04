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
  return (
    <details className="review-settings" id="review-suggestion-settings">
      <summary>
        <span>
          <SlidersHorizontal size={18} strokeWidth={1.6} aria-hidden="true" />
          <strong>Suggestion settings</strong>
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </summary>
      <div className="review-settings-body">
        <p>Choose the details to look for. Saving changes starts a fresh review.</p>
        <div className="review-setting-choices">
          <DetectionControls prefix="review" variant="checkbox" disabled={disabled}
            disabledReason="Wait for the current review changes to finish saving."
            categories={[...(review.emailEnabled ? ['email' as const] : []), ...(review.phoneEnabled ? ['phone' as const] : []), ...review.extraCategories]}
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
            onClick={() => void review.saveSettings()}
            disabled={!review.settingsDirty || review.dirty || disabled || review.conflict}
          >
            {review.settingsPending ? 'Saving settings…' : 'Save suggestion settings'}
          </button>
        </div>
        <ReviewRules review={review} csrf={csrf} />
      </div>
    </details>
  )
}
