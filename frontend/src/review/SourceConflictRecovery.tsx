import { GitCompareArrows, RefreshCw, ShieldCheck } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import './source-recovery.css'

export function SourceConflictRecovery({ review }: { review: ReviewController }) {
  const recovery = review.sourceRecovery
  if (!review.conflict || !review.dirty) return null
  return (
    <section
      className="source-conflict"
      id="source-save-error"
      aria-labelledby="source-conflict-title"
    >
      <div className="source-conflict-heading" role="alert">
        <span className="source-conflict-icon">
          <GitCompareArrows size={20} aria-hidden="true" />
        </span>
        <div>
          <h3 id="source-conflict-title">A newer version is saved</h3>
          <p>The saved text, findings, or settings changed while this tab was open.</p>
        </div>
      </div>
      <p className="source-conflict-preserved">
        <ShieldCheck size={15} aria-hidden="true" /> Your edits are still here.
      </p>
      {recovery.comparison ? (
        <div className="source-comparison">
          <p>Compare both versions before deciding how to continue.</p>
          <div className="source-comparison-panes">
            <div><h4 id="local-source-title">Your unsaved text <span>In this tab</span></h4><pre className="source-comparison-text" tabIndex={0} role="region" aria-labelledby="local-source-title">{review.text}</pre></div>
            <div><h4 id="latest-source-title">Latest saved text <span>On the server</span></h4><pre className="source-comparison-text" tabIndex={0} role="region" aria-labelledby="latest-source-title">{recovery.comparison.saved.text}</pre></div>
          </div>
          <p>
            Continuing keeps your editor text. Saving a new revision will replace the current
            source and reset its findings and review confirmation.
          </p>
          <div className="source-conflict-actions">
            <button type="button" disabled={review.actionPending || recovery.pending} onClick={recovery.cancel}>
              Cancel comparison
            </button>
            <button
              type="button"
              className="button-primary"
              disabled={review.actionPending || recovery.pending}
              onClick={recovery.keepEdits}
            >
              Continue with my edits
            </button>
          </div>
        </div>
      ) : (
        <div className="source-conflict-refresh">
          <p>
            Load the latest saved version while keeping your editor text. You can check any
            source changes before saving.
          </p>
          <button
            type="button"
            className="button-primary"
            disabled={review.actionPending || recovery.pending}
            onClick={() => void recovery.refresh()}
          >
            <RefreshCw size={15} aria-hidden="true" />
            {recovery.pending ? 'Loading latest version…' : 'Load latest & keep edits'}
          </button>
        </div>
      )}
      {recovery.error && (
        <p className="source-recovery-error" role="alert">{recovery.error}</p>
      )}
    </section>
  )
}
