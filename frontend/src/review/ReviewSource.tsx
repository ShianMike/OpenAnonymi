import { useMemo, useState } from 'react'
import { categoryPresentation, findingCategories } from '../rules/categoryPresentation'
import { Pencil, Check, MousePointer2, CircleHelp, Tag, Eye } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { StudioSelect } from './studio/StudioControls'
import { ReviewText } from './ReviewText'
import { SourceConflictRecovery } from './SourceConflictRecovery'
import { ReviewReloadButton } from './ReviewReloadButton'
import { FileLayoutView } from './layout/FileLayoutView'

export function ReviewSource({ review }: { review: ReviewController }) {
  const [layoutVisible, setLayoutVisible] = useState(true)
  const { state, editingSource, setEditingSource, text, dirty, pending, sourceRef, selection } =
    review
  const marks = useMemo(() => review.activeFindings.map((finding) => ({ span: finding.span, finding })), [review.activeFindings])
  if (state.kind !== 'ready') return null
  const fixedLayout = state.saved.file_format === 'pdf'
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
          <h2>{fixedLayout ? 'PDF document' : 'Source text'}</h2>
          <span className="document-badge">{dirty ? 'Unsaved edits' : 'Private source'}</span>
        </div>
        <div className="document-heading-actions">
          {fixedLayout && !editingSource && <div className="file-view-switch" role="group" aria-label="Source display">
            <button type="button" aria-pressed={layoutVisible} onClick={() => setLayoutVisible(true)}>Page layout</button>
            <button type="button" aria-pressed={!layoutVisible} onClick={() => setLayoutVisible(false)}>Text view</button>
          </div>}
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
            {editingSource ? 'View document' : review.canEdit && !fixedLayout ? 'Edit text' : 'Mark text'}
          </button>
        </div>
      </div>
      {!editingSource && (
        <>
          <p className="document-help">
            <MousePointer2 size={14} aria-hidden="true" />
            {fixedLayout ? 'Select a highlighted detail to review it, or use Mark text to add one.' : 'Click a highlighted detail to choose what to share.'}
          </p>
          {fixedLayout && layoutVisible ? review.mobilePanel === 'original' ? <FileLayoutView review={review} variant="original"/> : null :
          <ReviewText
            text={state.saved.text}
            marks={marks}
            review={review}
            variant="original"
          />}
          <div className="document-legend" aria-label="Highlight legend">
            <strong>Highlights</strong>
            <span data-action="pending"><CircleHelp size={15} aria-hidden="true" /> Needs a choice</span>
            <span data-action="changed"><Tag size={15} aria-hidden="true" /> Hidden or replaced</span>
            <span data-action="keep"><Eye size={15} aria-hidden="true" /> Kept as written</span>
          </div>
        </>
      )}
      <div hidden={!editingSource} className="document-editor">
        {state.saved.structure === 'simplified' && <p className="field-note" role="status">This edit changed the Word layout; the Word download will use plain paragraphs.</p>}
        <p className="document-help">
          {fixedLayout ? 'Select text to mark a detail. Upload a revised file to change the source while keeping its layout.' : review.canEdit ? 'Select text to mark a detail, or edit the source and save a new revision.' : 'Select text to mark a detail. The owner manages source revisions.'}
        </p>
        <label htmlFor="saved-source" className="sr-only">
          Text to review
        </label>
        <textarea
          id="saved-source"
          className="source-editor"
          value={text}
          readOnly={!review.canEdit || fixedLayout}
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
            <StudioSelect
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
            </StudioSelect>
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
            {review.canEdit && !fixedLayout && <button
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
