import { CheckCircle2, Sparkles, RotateCw, ChevronDown } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { ReviewSetup } from './ReviewSetup'
import { LoadingState } from '../loading/LoadingState'

export function ReviewSuggestions({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  const { scan } = review
  const complete = scan?.status === 'completed'
  const blocked = review.dirty || review.settingsDirty || review.actionPending || review.conflict
  return (
    <section className="review-suggestions" aria-labelledby="suggestions-heading">
      <div className="scan-heading">
        <span className="scan-icon">
          {complete ? (
            <CheckCircle2 size={18} strokeWidth={1.6} aria-hidden="true" />
          ) : (
            <Sparkles size={18} strokeWidth={1.5} aria-hidden="true" />
          )}
        </span>
        <div>
          <h2 id="suggestions-heading">
            {complete ? 'Suggestions checked' : review.canEdit ? 'Find sensitive details' : 'Suggestion status'}
          </h2>
          <p>
            {complete
              ? `${scan.match_count || 0} possible details found. You choose what to share.`
              : 'Check the categories chosen for this review.'}
          </p>
        </div>
      </div>
      <div className="scan-actions">
        {!complete && review.canEdit && (
          <button
            className="button-primary"
            type="button"
            disabled={blocked || scan?.status === 'scanning'}
            onClick={() => void review.scanDraft()}
          >
            {review.scanPending
              ? 'Scanning…'
              : scan?.status === 'failed'
                ? 'Retry scan'
                : 'Find suggestions'}
          </button>
        )}
        <button
          className="quiet-icon"
          type="button"
          disabled={review.dirty || review.actionPending}
          aria-label="Refresh scan status"
          onClick={() => void review.refreshScan()}
        >
          <RotateCw size={16} aria-hidden="true" />
        </button>
      </div>
      {scan?.status === 'scanning' && (
        <div><LoadingState label="Checking for sensitive details…" compact
          slowMessage="Suggestions are still being checked. Refresh to check their status." />
          <p className="field-note">Use refresh to check when suggestions are ready.</p>
        </div>
      )}
      {scan?.status === 'failed' && (
        <p role="alert">The scan could not finish. {review.canEdit ? 'Retry when you are ready.' : 'The owner can retry suggestions; you can still mark details manually.'}</p>
      )}
      {!review.canEdit && !complete && scan?.status !== 'scanning' && scan?.status !== 'failed' && (
        <p className="field-note">The owner runs suggestions. You can mark details yourself while reviewing the text.</p>
      )}
      {complete && scan.match_count === 0 && (
        <p className="scan-empty-note">
          No suggestions found. Review the full text before sharing.
        </p>
      )}
      {complete && scan.dropped_suggestions > 0 && <p className="field-note" role="status">
        {scan.dropped_suggestions} suggestions crossed Word paragraph or cell boundaries and were not added; mark them manually if needed.
      </p>}
      {complete && scan.suggestions.length > 0 && (
        <details className="scan-explanations">
          <summary>
            Why these details? <ChevronDown size={14} aria-hidden="true" />
          </summary>
          <ul>
            {scan.suggestions.map((item) => (
              <li key={item.finding_id}>
                <button
                  type="button"
                  onClick={() => review.locateFinding(item.finding_id, 'source')}
                  disabled={review.dirty || review.settingsDirty}
                >
                  {review.codePoints.slice(item.span.start, item.span.end).join('')}
                </button>
                <span>{item.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <ReviewSetup review={review} />
    </section>
  )
}
