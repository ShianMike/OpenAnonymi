import { ShieldCheck, ArrowRight, Copy, Download, CheckCircle2 } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { sameVersion } from './reviewState'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { LoadingMark } from '../loading/LoadingMark'
import { ReviewerCompletion } from '../team/ReviewerCompletion'
import { useState } from 'react'
import { GlassSelect } from '../ui/GlassSelect'

const styleCountLabels: Record<string, string> = { stand_in: 'Fictional stand-ins', date_shift: 'Shifted dates', partial_mask: 'Partial masks', generalize: 'Generalized dates' }

export function ReviewCompletion({ review }: { review: ReviewController }) {
  const [format, setFormat] = useState<'txt' | 'docx'>('txt')
  const { state, canConfirm, canExport, currentSummary, preparedDownload } = review
  if (state.kind !== 'ready') return null
  if (!review.canEdit) return <ReviewerCompletion review={review} />
  const confirmed =
    (state.saved.status === 'ready' || state.saved.status === 'exported') &&
    !review.dirty &&
    !review.settingsDirty &&
    !review.conflict
  return (
    <section className="review-completion" aria-labelledby="completion-heading">
      <div className="completion-heading">
        <span className="completion-icon">
          <ShieldCheck size={21} strokeWidth={1.4} aria-hidden="true" />
        </span>
        <div>
          <span className="review-eyebrow">SHARE WITH CARE</span>
          <h2 id="completion-heading">
            {confirmed ? 'Your reviewed version is ready' : 'A final look before sharing'}
          </h2>
        </div>
        {confirmed && <CheckCircle2 size={20} aria-hidden="true" />}
      </div>
      <p>
        Read the full reviewed output, including unmarked passages. Context can still identify
        someone.
      </p>
      {!confirmed && review.canEdit && (
        <div className="completion-confirmation">
          <GlassCheckbox
            id="confirm-output"
            label="I reviewed the full output and confirm this version."
            description={review.handoff.value?.require_approval ? 'Copying and downloading also require the assigned reviewer’s approval.' : 'Confirming unlocks copying and downloading.'}
            checked={review.confirmedPreview}
            disabled={!canConfirm}
            onCheckedChange={review.setConfirmedPreview}
          />
          <button
            type="button"
            className="button-primary"
            onClick={() => void review.completeReview()}
            disabled={!canConfirm || !review.confirmedPreview}
          >
            {review.completionPending ? 'Confirming…' : 'Confirm review'}
            {review.completionPending ? <LoadingMark small /> : <ArrowRight size={16} aria-hidden="true" />}
          </button>
        </div>
      )}
      {!confirmed && !canConfirm && review.canEdit && (
        <p role="status" className="completion-status">
          {review.conflict
            ? 'Load the latest saved review before confirming.'
            : review.dirty || review.settingsDirty
              ? 'Save your changes before confirming.'
            : review.pendingFindings.length
              ? `${review.pendingFindings.length} ${review.pendingFindings.length === 1 ? 'detail needs' : 'details need'} a decision before you can confirm.`
              : 'Finish the scan and resolve any overlapping findings before confirming.'}
        </p>
      )}
      {confirmed && (
        <p role="status" className="completion-status">
          This version and its decisions are confirmed.
        </p>
      )}
      {confirmed && review.handoff.value?.require_approval && !review.handoff.exportApproved && <p className="completion-status" role="status">Waiting for the assigned reviewer to approve this exact version before export.</p>}
      <div className="completion-export">
        <button
          type="button"
          onClick={() => void review.copyReviewedOutput()}
          disabled={!canExport}
        >
          {review.exportPending ? <LoadingMark small /> : <Copy size={16} aria-hidden="true" />}
          {review.exportPending ? 'Preparing output…' : 'Copy reviewed text'}
        </button>
        <div><label className="field-label" htmlFor="download-format">Download format</label>
          <GlassSelect id="download-format" value={format} disabled={review.exportPending}
            onValueChange={(value) => setFormat(value as typeof format)}>
            <option value="txt">Plain text (TXT)</option><option value="docx">Word (DOCX)</option>
          </GlassSelect></div>
        <button
          type="button"
          onClick={() => void review.downloadReviewedOutput(format)}
          disabled={!canExport}
        >
          {review.exportPending ? <LoadingMark small /> : <Download size={16} aria-hidden="true" />}
          {review.exportPending ? 'Preparing output…' : format === 'txt' ? 'Generate reviewed TXT' : 'Generate reviewed Word'}
        </button>
      </div>
      {preparedDownload &&
        canExport &&
        sameVersion(preparedDownload.version, state.saved.version) && (
          <p>
            <a href={preparedDownload.url} download={preparedDownload.filename}>
              {preparedDownload.format === 'txt' ? 'Save reviewed TXT' : 'Save reviewed Word'}
            </a>
          </p>
        )}
      {currentSummary && !review.dirty && !review.settingsDirty && (
        <details className="review-summary-details">
          <summary>
            Review summary · {currentSummary.finding_count}{' '}
            {currentSummary.finding_count === 1 ? 'detail' : 'details'}
          </summary>
          <div aria-label="Review summary">
            <p>
              {Object.entries(currentSummary.counts_by_action)
                .map(
                  ([action, count]) =>
                    `${count} ${action === 'label' ? 'labeled' : action === 'redact' ? 'redacted' : 'kept'}`,
                )
                .join(' · ') || 'No findings marked'}
            </p>
            <dl className="summary-style-counts">{Object.entries(currentSummary.counts_by_action_and_style).flatMap(([action, styles]) =>
              Object.entries(styles).filter(([, count]) => count > 0).map(([style, count]) => <div key={`${action}-${style}`}><dt>{styleCountLabels[style] ?? (action === 'label' ? 'Category labels' : action === 'redact' ? '[REDACTED]' : 'Original text kept')}</dt><dd>{count}</dd></div>))}</dl>
            {currentSummary.fictional_replacements > 0 && <p>{currentSummary.fictional_replacements} replacements are fictional stand-ins; they are not real people, organizations, places or contacts.</p>}
            <p>
              Confirmed {new Date(currentSummary.confirmed_at).toLocaleString()}.{' '}
              {currentSummary.last_output_generated_at
                ? `Output last generated ${new Date(currentSummary.last_output_generated_at).toLocaleString()}.`
                : 'Output has not been generated yet.'}
            </p>
          </div>
        </details>
      )}
    </section>
  )
}
