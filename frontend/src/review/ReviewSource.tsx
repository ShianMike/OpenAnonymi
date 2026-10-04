import { useMemo } from 'react'
import { categoryPresentation, findingCategories } from '../rules/categoryPresentation'
import { FileText, Pencil, Check, MousePointer2 } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { GlassTextarea } from '../ui/GlassTextarea'
import { GlassSelect } from '../ui/GlassSelect'
import { ReviewText } from './ReviewText'
import { SourceConflictRecovery } from './SourceConflictRecovery'
import { ReviewReloadButton } from './ReviewReloadButton'

export function ReviewSource({ review }: { review: ReviewController }) {
  const { state, editingSource, setEditingSource, text, dirty, pending, sourceRef, selection } =
    review
  const marks = useMemo(() => review.activeFindings.map((finding) => ({ span: finding.span, finding })), [review.activeFindings])
  if (state.kind !== 'ready') return null
  return (
    <form
      className="review-source"
      id="review-original-panel"
      role="tabpanel"
      aria-labelledby="review-original-tab"
      onSubmit={review.save}
    >
      <div className="document-panel-heading">
        <div>
          <FileText size={19} strokeWidth={1.5} aria-hidden="true" />
          <h2>Original text</h2>
          <span className="document-badge">{dirty ? 'Unsaved edits' : 'Private source'}</span>
        </div>
        <button
          type="button"
          className="document-edit-button"
          disabled={dirty || review.actionPending}
          onClick={() => {
            setEditingSource(!editingSource)
            review.setSelection(null)
          }}
        >
          {editingSource ? (
            <Check size={15} aria-hidden="true" />
          ) : (
            <Pencil size={15} aria-hidden="true" />
          )}
          {editingSource ? 'View highlights' : review.canEdit ? 'Edit / mark text' : 'Mark text'}
        </button>
      </div>
      {!editingSource && (
        <>
          <p className="document-help">
            <MousePointer2 size={14} aria-hidden="true" /> Click a highlighted detail to choose what
            to share.
          </p>
          <ReviewText
            text={state.saved.text}
            marks={marks}
            review={review}
            variant="original"
          />
          <div className="document-legend" aria-label="Highlight legend">
            <span>Needs decision</span>
            <span>Label / redact</span>
            <span>Kept</span>
          </div>
        </>
      )}
      <div hidden={!editingSource} className="document-editor">
        {state.saved.structure === 'simplified' && <p className="field-note" role="status">This edit changed the Word layout; the Word download will use plain paragraphs.</p>}
        <p className="document-help">
          {review.canEdit ? 'Select text to mark a detail, or edit the source and save a new revision.' : 'Select text to mark a detail. The owner manages source revisions.'}
        </p>
        <label htmlFor="saved-source" className="sr-only">
          Text to review
        </label>
        <GlassTextarea
          id="saved-source"
          className="source-editor"
          value={text}
          readOnly={!review.canEdit}
          ref={sourceRef}
          disabled={review.actionPending}
          aria-describedby={
            dirty
              ? [review.conflict && 'source-save-error', review.error && 'source-action-error']
                  .filter(Boolean).join(' ') || undefined
              : undefined
          }
          onMouseUp={review.captureSelection}
          onKeyUp={review.captureSelection}
          onChange={(event) => {
            review.setText(event.target.value)
            review.setSelection(null)
            review.setNotice(null)
            review.setConfirmedPreview(false)
            review.setPreparedDownload(null)
          }}
        />
        {selection && !dirty && (
          <div className="selection-tools">
            <span>{selection.end - selection.start} characters selected</span>
            <label className="sr-only" htmlFor="selection-category">
              Finding category
            </label>
            <GlassSelect
              id="selection-category"
              value={review.manualCategory}
              onValueChange={(value) =>
                review.setManualCategory(value as typeof review.manualCategory)
              }
            >
              {findingCategories.map(
                (category) => (
                  <option key={category} value={category}>
                    {categoryPresentation[category as keyof typeof categoryPresentation].label}
                  </option>
                ),
              )}
            </GlassSelect>
            <button
              type="button"
              className="button-primary"
              onClick={() => void review.changeFinding('add')}
              disabled={
                review.selectionOverlaps ||
                review.actionPending ||
                review.conflict ||
                review.settingsDirty
              }
            >
              Mark selected detail
            </button>
            {review.selectionOverlaps && (
              <p>
                This selection overlaps a finding. Use its advanced controls to correct the range.
              </p>
            )}
          </div>
        )}
        <div className="document-editor-footer">
          <span role="status">
            {Array.from(text).length.toLocaleString()} characters ·{' '}
            {dirty ? 'Unsaved edits' : 'Saved'}
          </span>
          <div>
            {review.canEdit && <button
              type="submit"
              className="button-primary"
              disabled={!review.canEdit || !dirty || review.actionPending || review.conflict}
            >
              {pending ? 'Saving…' : 'Save new revision'}
            </button>}
            {dirty && (
              <button type="button" onClick={() => void review.copyUnsaved()}>
                Copy unsaved edits
              </button>
            )}
            <ReviewReloadButton review={review} />
          </div>
        </div>
        <SourceConflictRecovery review={review} />
        {review.error && dirty && (
          <p id="source-action-error" role="alert">
            {review.error}
          </p>
        )}
      </div>
    </form>
  )
}
