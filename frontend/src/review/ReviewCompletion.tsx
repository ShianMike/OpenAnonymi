import { useId, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowUpRight, Check, ChevronDown, Copy, Download, Eye, LockKeyhole } from 'lucide-react'
import type { ReviewedFormat } from '../api/client'
import type { ReviewController } from './useReviewController'
import { StudioDialog } from './studio/StudioControls'
import { sameVersion } from './reviewState'
import { ReviewerCompletion } from '../team/ReviewerCompletion'
import { readReviewedOutput } from '../team/reviewerNavigation'

const formats: { value: ReviewedFormat; name: string; extension: string; detail: string }[] = [
  { value: 'txt', name: 'Plain text', extension: 'TXT', detail: 'Text with exact spacing' },
  { value: 'docx', name: 'Word document', extension: 'DOCX', detail: 'Editable document' },
  { value: 'pdf', name: 'PDF document', extension: 'PDF', detail: 'Ready for sharing' },
  { value: 'report', name: 'Review report', extension: 'JSON', detail: 'A record of your decisions' },
]
const styleCountLabels: Record<string, string> = { stand_in: 'Fictional stand-ins', date_shift: 'Shifted dates', partial_mask: 'Partial masks', generalize: 'Generalized dates' }

export function ReviewCompletion({ review }: { review: ReviewController }) {
  const [open, setOpen] = useState(false)
  if (review.state.kind !== 'ready') return null
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><button type="button" className="studio-primary studio-export-trigger"><span>{review.canExport ? 'Export' : review.canEdit ? 'Review & export' : 'Complete review'}</span><ArrowUpRight size={16} /></button></Dialog.Trigger>
    <StudioDialog title={review.canEdit ? 'Export review' : 'Complete your review'} description={review.state.saved.title || 'Untitled review'} busy={review.completionPending || review.exportPending} className="studio-export-dialog">
      <div className="studio-dialog-body">{review.canEdit ? <ReviewCompletionBody review={review} onRead={() => setOpen(false)} /> : <ReviewerCompletion review={review} />}</div>
    </StudioDialog>
  </Dialog.Root>
}

export function ReviewCompletionBody({ review, onRead }: { review: ReviewController; onRead?: () => void }) {
  const formatId = useId()
  const [format, setFormat] = useState<ReviewedFormat>(() => review.state.kind === 'ready' && review.state.saved.file_format ? review.state.saved.file_format : 'txt')
  const { state, canConfirm, canExport, currentSummary, preparedDownload } = review
  if (state.kind !== 'ready') return null
  const confirmed = (state.saved.status === 'ready' || state.saved.status === 'exported') && !review.dirty && !review.settingsDirty && !review.decisionPending && !review.conflict
  const confirmationReason = review.conflict ? 'Load the latest saved review before confirming.'
    : review.actionPending ? 'Wait for changes and output to finish saving.'
    : review.dirty ? 'Save your text changes before confirming.'
    : review.settingsDirty ? 'Save your suggestion settings before confirming.'
    : review.scan?.status !== 'completed' ? 'Find suggestions first, then review the highlighted details.'
    : review.pendingFindings.length ? `${review.pendingFindings.length} ${review.pendingFindings.length === 1 ? 'detail needs' : 'details need'} your choice before confirming.`
    : review.findings?.overlaps.length ? 'Correct overlapping highlights before continuing.'
    : !canConfirm ? 'Wait for the reviewed output to finish updating.' : 'Read the full text, including anything without highlights.'
  const exportReason = review.actionPending ? 'Wait for changes and output to finish saving.'
    : confirmed && !review.handoff.exportApproved ? 'Waiting for approval from the assigned reviewer for this exact version.'
    : 'Confirm this version to enable export.'
  const selected = formats.find(item => item.value === format)!
  const readyDownload = preparedDownload && canExport && !review.exportPending && preparedDownload.format === format &&
    sameVersion(preparedDownload.version, state.saved.version) ? preparedDownload : null
  const formatNote = format === 'pdf' ? state.saved.file_format === 'pdf'
    ? 'Keeps page sizes, positions and appearance. Redactions are flattened into page images. Original text layers, attachments, forms and annotations are removed; the PDF is not searchable.'
    : 'Creates a PDF with plain paragraphs, page wrapping and expanded tabs. Choose TXT to preserve exact whitespace.'
    : format === 'docx' ? state.saved.file_format === 'docx' ? 'Keeps supported Word structure. Editing the source text can simplify its layout.' : 'Creates an editable Word document from the reviewed text.'
    : format === 'report' ? 'A JSON report of categories, actions, styles and positions in this confirmed review.'
    : 'Preserves tabs, spaces and line endings in the reviewed text.'
  return <section className="studio-export-content" aria-label="Check and export" aria-busy={review.exportPending || review.completionPending}>
    <div className="studio-export-review" data-confirmed={confirmed}>
      <div className="studio-export-status"><div className="studio-export-status-copy">
        <h3>{confirmed ? canExport ? 'Ready to share' : 'Review confirmed' : 'One final check'}</h3>
        <span className="studio-export-state">{confirmed ? <Check size={12} aria-hidden="true" /> : <LockKeyhole size={12} aria-hidden="true" />}{confirmed ? 'Confirmed' : 'Confirmation required'}</span>
        {!canExport && <p>{confirmed ? exportReason : confirmationReason}</p>}
      </div>
      {(canConfirm || confirmed) && <button type="button" className="studio-read-output" disabled={review.actionPending} onClick={() => { readReviewedOutput(review); onRead?.() }}><Eye size={15} aria-hidden="true" />Preview output<ArrowUpRight size={14} aria-hidden="true" /></button>}
      </div>
    {!confirmed && <div className="studio-confirm-output"><label><input type="checkbox" id="confirm-output" checked={review.confirmedPreview} disabled={!canConfirm} onChange={event => review.setConfirmedPreview(event.target.checked)} />
      <span><strong>I reviewed the full output and confirm this version.</strong><small>{review.handoff.value?.require_approval ? 'Export also requires the assigned reviewer’s approval.' : 'Your original document remains unchanged.'}</small></span></label>
      <button type="button" className="studio-primary" disabled={!canConfirm || !review.confirmedPreview} title={!canConfirm ? confirmationReason : undefined} onClick={() => void review.completeReview()}>{review.completionPending ? 'Confirming…' : 'Confirm review'}<Check size={15} /></button>
    </div>}
    {confirmed && review.handoff.value?.require_approval && !review.handoff.exportApproved && <p role="status" id="completion-approval-status" className="studio-warn">{exportReason} {!review.handoff.value.reviewer_active && 'Assign an active reviewer using Collaborate.'}</p>}
    </div>
    <fieldset className="studio-export-formats" aria-describedby={`${formatId}-note`} disabled={review.exportPending}>
      <legend>File format</legend><div className="studio-format-options">
        {formats.map(item => <label key={item.value} className="studio-format-option">
          <input type="radio" name={formatId} value={item.value} checked={format === item.value} onChange={() => setFormat(item.value)} />
          <span><strong>{item.name}</strong><small>{item.value === 'pdf' && state.saved.file_format === 'pdf' ? 'Keep page layout' : item.detail}</small></span><span className="studio-format-extension">{item.extension}</span>
        </label>)}
      </div>
    </fieldset>
    <p className="studio-format-note" id={`${formatId}-note`}>{formatNote}</p>
    {review.error && <p role="alert" className="studio-error">{review.error}</p>}
    {currentSummary && !review.dirty && !review.settingsDirty && <details className="studio-export-summary"><summary><span>Review summary <small>{currentSummary.finding_count} details</small></span><ChevronDown size={14} aria-hidden="true" /></summary>
      <div className="studio-summary-body">
      <dl className="studio-summary-counts" aria-label="Decisions in this version">{([['label', 'Replaced'], ['redact', 'Hidden'], ['keep', 'Kept']] as const).map(([action, label]) =>
        <div key={action}><dt>{label}</dt><dd>{currentSummary.counts_by_action[action] ?? 0}</dd></div>)}</dl>
      {currentSummary.finding_count > 0 ? <><h4>Applied styles</h4><dl className="studio-summary-styles">{Object.entries(currentSummary.counts_by_action_and_style).flatMap(([action, styles]) =>
        Object.entries(styles).filter(([, count]) => count > 0).map(([style, count]) => <div key={`${action}-${style}`}><dt>{styleCountLabels[style] ?? (action === 'label' ? 'Category labels' : action === 'redact' ? 'Hidden with [REDACTED]' : 'Kept as written')}</dt><dd>{count}</dd></div>))}</dl>
      </> : <p>No findings were marked. Your confirmation applies to the full output.</p>}
      {currentSummary.fictional_replacements > 0 && <p>{currentSummary.fictional_replacements} fictional replacements. These are not real people, organizations, places or contacts.</p>}
      <dl className="studio-summary-times"><div><dt>Confirmed</dt><dd><time dateTime={currentSummary.confirmed_at}>{new Date(currentSummary.confirmed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></dd></div>
        {currentSummary.last_output_generated_at && <div><dt>Output prepared</dt><dd><time dateTime={currentSummary.last_output_generated_at}>{new Date(currentSummary.last_output_generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></dd></div>}
      </dl></div></details>}
    <footer className="studio-export-actions">
      <p role="status">{readyDownload ? <><Check size={13} aria-hidden="true" />{selected.extension} ready to save</> : review.exportPending ? 'Preparing output…' : canExport ? 'Prepare the file, then save it to your device.' : exportReason}</p>
      <div><button type="button" className="studio-copy-output" disabled={!canExport} title={!canExport ? exportReason : undefined} onClick={() => void review.copyReviewedOutput()}><Copy size={15} aria-hidden="true" />Copy reviewed text</button>
        {readyDownload ? <a className="studio-download-link" href={readyDownload.url} download={readyDownload.filename}>Save {selected.extension}<Download size={16} aria-hidden="true" /></a>
          : <button type="button" className="studio-primary" disabled={!canExport} title={!canExport ? exportReason : undefined} onClick={() => void review.downloadReviewedOutput(format)}>{review.exportPending ? 'Preparing…' : 'Prepare download'}<Download size={16} aria-hidden="true" /></button>}
      </div>
    </footer>
  </section>
}
