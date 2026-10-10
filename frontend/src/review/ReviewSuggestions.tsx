import { ArrowRight, CheckCircle2, ScanLine, Sparkles, ChevronDown } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { ReviewSetup } from './ReviewSetup'
import { LoadingState } from '../loading/LoadingState'
import { CsvReview } from './CsvReview'
import { DisabledReason } from '../ui/DisabledReason'
import { cn } from '../ui/cn'
import { RefreshButton } from '../ui/WorkspaceControls'
import { detectionChoices } from '../detection/categories'

export function ReviewSuggestions({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  const { scan } = review
  const scanChoices = detectionChoices.filter(choice => review.state.kind === 'ready' && review.state.saved.categories.includes(choice.category))
  const complete = scan?.status === 'completed'
  const blocked = review.dirty || review.settingsDirty || review.actionPending || review.conflict
  const blockedReason = review.conflict ? 'Load the latest saved review first.'
    : review.dirty ? 'Save your text changes first.'
    : review.settingsDirty ? 'Save your suggestion settings first.'
    : 'Wait for your changes to finish saving.'
  return (
    <section id="review-suggestions" className={cn('review-suggestions', complete && 'is-complete')} aria-labelledby="suggestions-heading">
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
            {complete ? review.dirty || review.settingsDirty ? 'Changes to save' : 'Suggestions ready' : review.canEdit ? 'Check for private details' : 'Suggestion status'}
          </h2>
          <p>
            {complete
              ? `${scan.match_count || 0} possible ${scan.match_count === 1 ? 'detail' : 'details'} found. You choose what to share.`
              : 'Start with suggestions. You choose what to change.'}
          </p>
        </div>
      </div>
      <div className="scan-actions">
        {!complete && review.canEdit && (
          <DisabledReason disabled={blocked || scan?.status === 'scanning'} reason={scan?.status === 'scanning' ? 'The check is running. Refresh to see its progress.' : blockedReason}><button
            className="button-primary"
            type="button"
            disabled={blocked || scan?.status === 'scanning'}
            onClick={() => void review.scanDraft()}
          >
            <ScanLine size={17} aria-hidden="true" />{review.scanPending || scan?.status === 'scanning'
              ? 'Scanning…'
              : scan?.status === 'failed'
                ? 'Retry scan'
                : 'Find suggestions'}<ArrowRight size={16} aria-hidden="true" />
          </button></DisabledReason>
        )}
        {scan && scan.status !== 'not_started' && <RefreshButton label="Refresh scan status" disabled={review.dirty || review.actionPending} onClick={() => void review.refreshScan()} />}
      </div>
      <div className="scan-scope">
        <div className="scan-scope-heading"><strong>Selected categories</strong>
        {review.canEdit && <button type="button" className="button-link" aria-label="Change detection categories" onClick={() => {
          const settings = document.getElementById('review-suggestion-settings') as HTMLDetailsElement | null
          if (settings) { settings.open = true; settings.scrollIntoView({ block: 'nearest' }); settings.querySelector<HTMLElement>('summary')?.focus() }
        }}>Change<ArrowRight size={14} aria-hidden="true" /></button>}</div>
        {scanChoices.length ? <ul className="scan-categories" aria-label="Categories to scan">
          {scanChoices.map(choice => <li key={choice.category}>{choice.label}</li>)}
        </ul> : <p className="scan-blocked-note">Manual findings only</p>}
        {scanChoices.length < detectionChoices.length && <p className="scan-scope-note">Other categories won’t be scanned.</p>}
      </div>
      {blocked && <p className="scan-blocked-note" role="status">{blockedReason}</p>}
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
      <CsvReview key={`${review.state.saved.version.source_revision_id}:${review.state.saved.version.settings_version}`} review={review} />
      <ReviewSetup review={review} />
    </section>
  )
}
