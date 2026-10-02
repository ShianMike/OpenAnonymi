import { Eye, AlignLeft, Highlighter } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { sameVersion } from './reviewState'
import { GlassTextarea } from '../ui/GlassTextarea'
import { ReviewText } from './ReviewText'
import { LoadingState } from '../loading/LoadingState'

export function ReviewPreview({ review }: { review: ReviewController }) {
  const { state, preview, plainPreview, setPlainPreview, activeFindings, previewRef } = review
  if (state.kind !== 'ready') return null
  const current =
    preview && sameVersion(preview.version, state.saved.version) && preview.text !== null
  return (
    <section
      className="review-preview"
      id="review-preview-panel"
      role="tabpanel"
      aria-labelledby="review-preview-tab"
    >
      <div className="document-panel-heading">
        <div>
          <Eye size={19} strokeWidth={1.5} aria-hidden="true" />
          <h2 id="preview-heading">Reviewed output</h2>
          <span className="document-badge">{review.canExport ? 'Confirmed' : 'Preview'}</span>
        </div>
        {current && (
          <button
            className="document-edit-button"
            type="button"
            onClick={() => setPlainPreview(!plainPreview)}
          >
            {plainPreview ? (
              <Highlighter size={15} aria-hidden="true" />
            ) : (
              <AlignLeft size={15} aria-hidden="true" />
            )}
            {plainPreview ? 'View highlights' : 'Plain text'}
          </button>
        )}
      </div>
      {review.dirty || review.settingsDirty ? (
        <p className="document-empty">Save your changes to refresh the reviewed output.</p>
      ) : preview?.status === 'conflict' ? (
        <p role="alert" className="document-empty">
          Overlapping findings need correction or removal before an output can be shown.
        </p>
      ) : current ? (
        <>
          <p className="document-help" role="status">
            {review.canExport
              ? 'Review confirmed. This is the version you can share.'
              : preview.status === 'incomplete'
                ? `${preview.unresolved_finding_ids.length} details still need a decision. This output is provisional.`
                : 'All marked details have decisions. Read the full output before confirming.'}
          </p>
          {!plainPreview && (
            <ReviewText
              text={preview.text as string}
              review={review}
              variant="preview"
              marks={preview.mappings.flatMap((mapping) => {
                const finding = activeFindings.find(
                  (item) => item.finding_id === mapping.finding_id,
                )
                return finding ? [{ span: mapping.preview_span, finding }] : []
              })}
            />
          )}
          <div hidden={!plainPreview}>
            <label className="sr-only" htmlFor="reviewed-preview">
              Reviewed output
            </label>
            <GlassTextarea
              id="reviewed-preview"
              className="source-editor"
              value={preview.text as string}
              ref={previewRef}
              readOnly
            />
          </div>
        </>
      ) : review.previewError ? (
        <p role="alert" className="document-empty">Preview unavailable: {review.previewError}</p>
      ) : (
        <LoadingState label="Preparing the reviewed output…" className="document-empty" compact />
      )}
      {review.previewError && !review.dirty && !review.settingsDirty && (
        <button
          type="button"
          onClick={() =>
            void review.refreshPreview(review.documentId as string, state.saved.version)
          }
        >
          Retry preview
        </button>
      )}
    </section>
  )
}
