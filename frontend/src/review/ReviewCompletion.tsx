import { ShieldCheck, ArrowRight, Copy, Download, CheckCircle2, Eye, LockKeyhole } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { sameVersion } from './reviewState'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { LoadingMark } from '../loading/LoadingMark'
import { ReviewerCompletion } from '../team/ReviewerCompletion'
import { useState } from 'react'
import { GlassSelect } from '../ui/GlassSelect'
import type { CsvVariant, ReviewedFormat } from '../api/client'
import { DisabledReason } from '../ui/DisabledReason'
import { readReviewedOutput } from '../team/reviewerNavigation'

const styleCountLabels: Record<string, string> = { stand_in: 'Fictional stand-ins', date_shift: 'Shifted dates', partial_mask: 'Partial masks', generalize: 'Generalized dates' }

export function ReviewCompletion({ review }: { review: ReviewController }) {
  const [format, setFormat] = useState<ReviewedFormat>('txt')
  const [csvVariant, setCsvVariant] = useState<CsvVariant>('spreadsheet_safe')
  const { state, canConfirm, canExport, currentSummary, preparedDownload } = review
  if (state.kind !== 'ready') return null
  if (!review.canEdit) return <ReviewerCompletion review={review} />
  const confirmed =
    (state.saved.status === 'ready' || state.saved.status === 'exported') &&
    !review.dirty &&
    !review.settingsDirty &&
    !review.decisionPending &&
    !review.conflict
  const confirmationReason = review.conflict ? 'Load the latest saved review before confirming.'
    : review.actionPending ? 'Wait for the current changes and reviewed output to finish saving.'
    : review.dirty ? 'Save your text changes before confirming.'
    : review.settingsDirty ? 'Save your suggestion settings before confirming.'
    : review.scan?.status !== 'completed' ? 'Find suggestions first, then choose what to change in each highlighted detail.'
    : review.pendingFindings.length ? `${review.pendingFindings.length} ${review.pendingFindings.length === 1 ? 'detail needs' : 'details need'} your choice before confirming.`
    : review.findings?.overlaps.length ? 'Some highlights overlap. Adjust them so each detail has one choice.'
    : !canConfirm ? 'Wait for the reviewed output to finish updating.'
    : 'Read the full output and check the confirmation box first.'
  const exportReason = review.actionPending ? 'Wait for the current changes and reviewed output to finish saving.'
    : confirmed && !review.handoff.exportApproved ? 'The assigned reviewer must approve this exact version.'
    : 'Confirm the current reviewed output before copying or downloading.'
  return (
    <section className="review-completion" aria-labelledby="completion-heading">
      <div className="completion-heading">
        <span className="completion-icon">
          <ShieldCheck size={21} strokeWidth={1.4} aria-hidden="true" />
        </span>
        <div>
          <span className="review-eyebrow">YOUR FINAL CHECK</span>
          <h2 id="completion-heading">
            {confirmed ? canExport ? 'Your reviewed version is ready' : 'Review confirmed' : 'Check, confirm, and share'}
          </h2>
        </div>
        {confirmed && <CheckCircle2 size={20} aria-hidden="true" />}
      </div>
      <div className="completion-next-step">
        <div><strong>{confirmed ? 'Your choices are saved for this version' : '1. Read the reviewed text'}</strong>
          <p role="status">{!confirmed && !canConfirm ? confirmationReason : 'Read every line, including text without highlights. Context can still identify someone.'}</p>
        </div>
        {(canConfirm || confirmed) && <button type="button" className="completion-read" disabled={review.actionPending}
          onClick={() => readReviewedOutput(review)}><Eye size={17} aria-hidden="true" /> Read reviewed output</button>}
      </div>
      {!confirmed && review.canEdit && (
        <>
        <h3 className="completion-step-heading">2. Confirm this version</h3>
        <div className="completion-confirmation">
          <GlassCheckbox
            id="confirm-output"
            label="I reviewed the full output and confirm this version."
            description={review.handoff.value?.require_approval ? 'Copying and downloading also require the assigned reviewer’s approval.' : 'Confirming unlocks copying and downloading.'}
            checked={review.confirmedPreview}
            disabled={!canConfirm}
            disabledReason={confirmationReason}
            onCheckedChange={review.setConfirmedPreview}
          />
          <DisabledReason disabled={!canConfirm || !review.confirmedPreview} reason={confirmationReason}><button
            type="button"
            className="button-primary"
            onClick={() => void review.completeReview()}
            disabled={!canConfirm || !review.confirmedPreview}
          >
            {review.completionPending ? 'Confirming…' : 'Confirm review'}
            {review.completionPending ? <LoadingMark small /> : <ArrowRight size={16} aria-hidden="true" />}
          </button></DisabledReason>
        </div>
        </>
      )}
      {confirmed && (
        <p role="status" className="completion-status">
          This version and its decisions are confirmed.
        </p>
      )}
      {confirmed && review.handoff.value?.require_approval && !review.handoff.exportApproved &&
        <p id="completion-approval-status" className="completion-status" role="status">
          {review.handoff.value.approval_policy === 'always'
            ? review.handoff.value.reviewer_active
              ? 'Your workspace requires the assigned reviewer to approve this exact version before export.'
              : 'Your workspace requires a reviewer to approve this version before export. Assign a reviewer.'
            : 'Waiting for the assigned reviewer to approve this exact version before export.'}
          {!review.handoff.value.reviewer_active && <> <a href="#review-handoff">Manage reviewer</a></>}
        </p>}
      <div className="completion-share-heading"><h3 className="completion-step-heading">{confirmed ? 'Copy or download' : '3. Copy or download'}</h3>
        {!canExport && <span><LockKeyhole size={14} aria-hidden="true" />{confirmed ? review.handoff.exportApproved ? 'Updating output' : 'Waiting for approval' : 'Confirm to unlock'}</span>}
      </div>
      <div className="completion-export">
        <DisabledReason disabled={!canExport} reason={exportReason}><button
          type="button"
          onClick={() => void review.copyReviewedOutput()}
          disabled={!canExport}
          aria-describedby={confirmed && review.handoff.value?.require_approval && !review.handoff.exportApproved ? 'completion-approval-status' : undefined}
        >
          {review.exportPending ? <LoadingMark small /> : <Copy size={16} aria-hidden="true" />}
          {review.exportPending ? 'Preparing output…' : 'Copy reviewed text'}
        </button></DisabledReason>
        <div><label className="field-label" htmlFor="download-format">Download format</label>
          <GlassSelect id="download-format" value={format} disabled={review.exportPending}
            onValueChange={(value) => setFormat(value as typeof format)}>
            <option value="txt">Plain text (TXT)</option><option value="docx">Word (DOCX)</option>
            <option value="pdf">PDF</option><option value="report">Redaction report (JSON)</option>
            {state.saved.csv && <option value="csv">CSV</option>}
          </GlassSelect></div>
        <DisabledReason disabled={!canExport} reason={exportReason}><button
          type="button"
          onClick={() => void review.downloadReviewedOutput(format, csvVariant)}
          disabled={!canExport}
          aria-describedby={confirmed && review.handoff.value?.require_approval && !review.handoff.exportApproved ? 'completion-approval-status' : undefined}
        >
          {review.exportPending ? <LoadingMark small /> : <Download size={16} aria-hidden="true" />}
          {review.exportPending ? 'Preparing output…' : { txt: 'Generate reviewed TXT', docx: 'Generate reviewed Word', pdf: 'Generate reviewed PDF', report: 'Generate redaction report', csv: 'Generate reviewed CSV' }[format]}
        </button></DisabledReason>
      </div>
      {canExport && !preparedDownload && <p className="field-note">Generate a file, then use its Save link to download it.</p>}
      {format === 'pdf' && <p className="field-note">PDF uses plain paragraphs with page wrapping and expanded tabs. TXT preserves exact whitespace.</p>}
      {format === 'report' && <p className="field-note">The report lists categories, actions, styles and positions in this confirmed review.</p>}
      {format === 'csv' && <div className="csv-export-options">
        <label className="field-label" htmlFor="csv-export-variant">CSV variant</label>
        <GlassSelect id="csv-export-variant" value={csvVariant} disabled={review.exportPending} onValueChange={(value) => setCsvVariant(value as CsvVariant)}>
          <option value="spreadsheet_safe">Spreadsheet-safe (default)</option><option value="unmodified">Unmodified cell values</option>
        </GlassSelect>
        {csvVariant === 'unmodified' && <p role="alert" className="field-note">Opening this file in a spreadsheet can run formulas from the data.</p>}
        <p className="field-note">Spreadsheet-safe CSV prefixes formula-leading cells with an apostrophe, including negative numbers. Apostrophes are visible to other programs. A spreadsheet can reactivate a formula after the file is edited and saved.</p>
      </div>}
      {preparedDownload &&
        canExport &&
        sameVersion(preparedDownload.version, state.saved.version) && (
          <p className="completion-download-ready" role="status">
            <a href={preparedDownload.url} download={preparedDownload.filename}>
              {preparedDownload.format === 'csv' ? `Save reviewed CSV (${preparedDownload.variant === 'unmodified' ? 'unmodified' : 'spreadsheet-safe'})` : { txt: 'Save reviewed TXT', docx: 'Save reviewed Word', pdf: 'Save reviewed PDF', report: 'Save redaction report' }[preparedDownload.format]}
            </a>
            {preparedDownload.format === 'csv' && <span> · {preparedDownload.prefixed ?? 0} cells prefixed</span>}
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
