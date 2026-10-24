import { ArrowRight, ScanLine, RefreshCw, Check } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { detectionChoices } from '../detection/categories'
import { ReviewSetup } from './ReviewSetup'
import { LoadingMark } from '../loading/LoadingMark'

export function ReviewSuggestions({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  const { scan } = review
  const complete = scan?.status === 'completed'
  const scanning = review.scanPending || scan?.status === 'scanning'
  const blocked = review.dirty || review.settingsDirty || review.actionPending || review.conflict
  const reason = review.conflict ? 'Reload the latest saved review first.' : review.dirty ? 'Save your text changes first.' : review.settingsDirty ? 'Save your suggestion settings first.' : 'Wait for your changes to finish saving.'
  const count = review.state.saved.categories.length
  return <section className="studio-scan" id="review-suggestions" aria-label="Suggestion status">
    <div className="studio-scan-status"><span>{scanning ? <LoadingMark small /> : complete ? <Check size={14} /> : <ScanLine size={14} />}{scanning ? 'Scanning…' : complete ? 'Scan complete' : scan?.status === 'failed' ? 'Scan failed' : 'Ready to scan'}</span>
      {scan && scan.status !== 'not_started' && <button type="button" className="studio-icon" disabled={blocked} aria-label="Refresh scan status" onClick={() => void review.refreshScan()}><RefreshCw size={14} /></button>}
    </div>
    <div className="studio-scan-scope"><span>{count === detectionChoices.length ? 'All categories' : `${count} selected categories`}</span>{review.canEdit && <button type="button" onClick={() => review.setSettingsOpen(true)} aria-label="Change detection categories">Configure <ArrowRight size={12} /></button>}</div>
    {!complete && review.canEdit && <button type="button" className="studio-primary studio-scan-start" aria-busy={scanning} disabled={blocked || scanning} onClick={() => void review.scanDraft()}>{scanning ? 'Scanning document…' : scan?.status === 'failed' ? 'Retry scan' : 'Find suggestions'}{!scanning && <ArrowRight size={15} />}</button>}
    {blocked && <p className="field-note" role="status">{reason}</p>}
    {scan?.status === 'scanning' && <p className="field-note" role="status">Suggestions appear automatically when ready.</p>}
    {scan?.status === 'failed' && <p role="alert" className="studio-error">The scan could not finish. {review.canEdit ? 'Retry when ready.' : 'The owner can retry; you can still mark details manually.'}</p>}
    {!review.canEdit && !complete && scan?.status !== 'scanning' && <p className="field-note">The owner runs suggestions. You can mark details manually.</p>}
    {complete && scan.dropped_suggestions > 0 && <p className="field-note" role="status">{scan.dropped_suggestions} suggestions crossed Word paragraph or cell boundaries and were not added; mark them manually if needed.</p>}
    {!review.canEdit && <><ReviewSetup review={review} /></>}
  </section>
}
