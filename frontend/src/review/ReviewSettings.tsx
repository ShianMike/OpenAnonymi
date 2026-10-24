import { SlidersHorizontal, ChevronDown } from 'lucide-react'
import { useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { StudioDialog, StudioSelect } from './studio/StudioControls'
import type { ReviewController } from './useReviewController'
import { ReviewRules } from '../rules/ReviewRules'
import '../rules/rules.css'
import { detectionChoices, extras } from '../detection/categories'
import { phoneRegions } from '../ui/phoneRegions'
import { ReviewSetup } from './ReviewSetup'
import { RetentionDialog } from '../retention/RetentionDialog'

export function ReviewSettings({ review, csrf }: { review: ReviewController; csrf: string }) {
  const [renewing, setRenewing] = useState<HTMLButtonElement | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  const disabled = review.actionPending
  const categories = [...(review.emailEnabled ? ['email' as const] : []), ...(review.phoneEnabled ? ['phone' as const] : []), ...review.extraCategories]
  return <><Dialog.Root open={review.settingsOpen} onOpenChange={open => { if (!disabled) review.setSettingsOpen(open) }}>
    <Dialog.Trigger asChild><button ref={trigger} type="button" id="review-suggestion-settings" className="studio-settings-trigger" disabled={disabled} aria-label={`Review settings, ${review.settingsDirty ? 'Unsaved changes' : `${categories.length} categories`}`}>
      <SlidersHorizontal size={16} /><span>Settings</span>{review.settingsDirty && <span className="studio-unsaved-dot" />}
    </button></Dialog.Trigger>
    <StudioDialog title="Review settings" description="Control what this review looks for." busy={disabled} className="studio-settings-dialog"
      onCloseAutoFocus={event => { if (renewing) event.preventDefault() }}>
      <div className="studio-dialog-body">
        <div className="studio-section-heading"><h3>Detect sensitive details</h3><span>{categories.length} / {detectionChoices.length} selected</span></div>
        <div className="studio-category-list">{detectionChoices.map(choice => <label className="studio-category" key={choice.category} title={choice.description}>
          <span>{choice.label}</span><input type="checkbox" checked={categories.includes(choice.category)} disabled={disabled}
            onChange={event => {
              const next = event.target.checked ? [...categories, choice.category] : categories.filter(value => value !== choice.category)
              review.setEmailEnabled(next.includes('email')); review.setPhoneEnabled(next.includes('phone')); review.setExtraCategories(extras(next))
              review.setConfirmedPreview(false); review.setPreparedDownload(null)
            }} />
        </label>)}</div>
        <p className="field-note">{categories.length ? 'Only selected categories are checked.' : 'No automatic checks. Mark details manually.'} Names and places are detected in English text.</p>
        <div className="studio-setting-row"><div><label htmlFor="scan-phone-region">Phone and date region</label><p>Interpret local numbers and date formats.</p></div>
          <StudioSelect id="scan-phone-region" value={review.phoneRegion} disabled={disabled} onValueChange={value => {
            review.setPhoneRegion(value); review.setConfirmedPreview(false); review.setPreparedDownload(null)
          }}>{phoneRegions.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</StudioSelect>
        </div>
        <ReviewSetup review={review} onRenew={() => { setRenewing(trigger.current); review.setSettingsOpen(false) }} />
        <details className="review-advanced-rules"><summary><span>Workspace rules<small>Custom detection rules used by this review</small></span><ChevronDown size={14} aria-hidden="true" /></summary><ReviewRules review={review} csrf={csrf} /></details>
        <p className="studio-warn">Saving changes resets suggestions and confirmation. Run the check again before exporting.</p>
        {review.error && <p role="alert" className="studio-error">{review.error}</p>}
      </div>
      <footer className="studio-dialog-footer"><span>{review.settingsDirty ? 'Unsaved changes' : 'Up to date'}</span>
        <Dialog.Close asChild><button type="button" disabled={disabled}>Done</button></Dialog.Close>
        <button type="button" className="studio-primary" aria-label="Save suggestion settings" onClick={() => void review.saveSettings()}
          disabled={!review.settingsDirty || review.dirty || disabled || review.conflict}>{review.settingsPending ? 'Saving…' : 'Save settings'}</button>
      </footer>
    </StudioDialog>
  </Dialog.Root>
    {renewing && <RetentionDialog key={`${saved.version.document_id}.${review.retentionCsrf}`} documentId={saved.version.document_id} csrf={review.retentionCsrf} returnFocus={renewing}
      onClose={() => setRenewing(null)} onSaved={value => { review.retentionRenewed(saved.version.document_id, value.expires_at); setRenewing(null) }} />}
  </>
}
