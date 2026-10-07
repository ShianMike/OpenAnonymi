import { Link, useLocation } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { StatusBadge } from '../ui/StatusBadge'
import { UnsavedNavigationPrompt } from '../ui/UnsavedNavigationPrompt'
import { useReviewController } from './useReviewController'
import { ReviewSuggestions } from './ReviewSuggestions'
import { ReviewDocument } from './ReviewDocument'
import { ReviewFindings } from './ReviewFindings'
import { ReviewCompletion } from './ReviewCompletion'
import { ReviewSettings } from './ReviewSettings'
import { AutosaveStatus } from '../recovery/AutosaveStatus'
import { HandoffPanel } from '../team/HandoffPanel'
import { FindingDiscussion } from '../team/FindingDiscussion'
import { ReviewerSteps } from '../team/ReviewerSteps'
import { useStickyReviewColumn } from './useStickyReviewColumn'
import './review-workspace.css'

export function EditDraftPage({
  session,
  onUnsavedChange,
}: {
  session: SessionView
  onUnsavedChange?: (dirty: boolean) => void
}) {
  const review = useReviewController(session)
  const location = useLocation()
  const fromContinue = Boolean(location.state && typeof location.state === 'object' && location.state.fromContinue === true)
  const batchParam = new URLSearchParams(location.search).get('batch')
  const fromBatch = batchParam && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(batchParam) ? batchParam : null
  const workspaceId = review.state.kind === 'ready' ? review.state.saved.workspace_id
    : session.memberships.find((item) => item.workspace_id === location.state?.workspaceId)?.workspace_id
  const backTo = fromBatch ? `/batches/${encodeURIComponent(fromBatch)}` : fromContinue ? `/continue${workspaceId ? `?workspace=${workspaceId}` : ''}` : '/documents'
  const stickyColumnRef = useStickyReviewColumn()
  const {
    state,
    error,
    notice,
    scan,
    lastFocusedRef,
    mobilePanel,
    dirty,
    settingsDirty,
    reloadSaved,
    pendingFindings,
  } = review
  return (
    <section
      className="review-page"
      aria-labelledby="review-title"
      onFocusCapture={(event) => {
        if (event.target instanceof HTMLElement) lastFocusedRef.current = event.target
      }}
    >
      <PageHeader
        title={state.kind === 'ready' ? state.saved.title || 'Untitled review' : 'Review workspace'}
        titleId="review-title"
        description="Decide what stays, then read the full output before sharing."
        action={<Link to={backTo}>{fromBatch ? 'Back to batch' : fromContinue ? 'Back to reviews' : 'Back to documents'}</Link>}
      />
      <UnsavedNavigationPrompt
        when={review.decisionPending || ((dirty || settingsDirty) && !review.recovery.protected)}
        saving={review.decisionPending}
        onWaitAndLeave={review.flushDecisions}
        focusBackId={dirty ? 'saved-source' : 'review-email'}
        onDirtyChange={onUnsavedChange}
        onSaveAndLeave={review.recovery.flush}
        onDiscardAndLeave={review.recovery.clear}
        onStay={() => {
          if (dirty) {
            review.setMobilePanel('original')
            review.setEditingSource(true)
          } else if (settingsDirty) {
            const settings = document.getElementById('review-suggestion-settings')
            if (settings instanceof HTMLDetailsElement) settings.open = true
          }
        }}
      />
      {state.kind === 'loading' && <LoadingState label="Loading the saved draft…" shape="document" description="Opening the source, saved decisions and reviewed output." />}
      {state.kind === 'error' && (
        <div role="alert">
          <p>{state.message}</p>
          {state.retryable !== false && (
            <button type="button" onClick={reloadSaved}>
              Retry
            </button>
          )}
        </div>
      )}
      {state.kind === 'ready' && (
        <>
          <div className="review-status-row">
            <div className="review-summary-strip" aria-label="Current review status">
              <StatusBadge status={state.saved.status} />
              {scan?.status === 'completed' ? (
                <span>
                  {pendingFindings.length > 0
                    ? `${pendingFindings.length} ${pendingFindings.length === 1 ? 'detail needs' : 'details need'} your choice`
                    : state.saved.status === 'ready' || state.saved.status === 'exported'
                      ? 'Review confirmed'
                      : review.activeFindings.length === 0
                        ? 'No suggestions found · Read the full text'
                        : 'Choices made · Check the reviewed output'}
                </span>
              ) : (
                <span>
                  {scan?.status === 'scanning' ? 'Looking for private details…' : scan?.status === 'failed' ? 'The check couldn’t finish · Retry suggestions' : 'Next: find suggestions, then choose what to change'}
                </span>
              )}
              {dirty && <span>Text changes not saved yet</span>}
              {settingsDirty && <span>Options not saved yet</span>}
              {review.decisionPending && <span role="status">Saving decisions · Output is updating</span>}
            </div>
            {review.canEdit && <AutosaveStatus recovery={review.recovery} dirty={dirty || settingsDirty} />}
          </div>
          <ReviewerSteps review={review} />
          {(error || review.conflict) && !dirty && (
            <div className="review-feedback is-error" role="alert">
              <span>{error || 'A newer review version is saved. Reload the latest review to continue.'}</span>
              {review.conflict && (
                <button type="button" onClick={reloadSaved}>
                  Reload latest review
                </button>
              )}
            </div>
          )}
          {notice && (
            <p className="review-feedback" role="status">
              {notice}
            </p>
          )}
          <div className="review-layout" data-mobile-panel={mobilePanel}>
            <div className="review-main-column" ref={stickyColumnRef}>
              <ReviewDocument review={review} userId={session.user_id} />
              <ReviewCompletion review={review} />
            </div>
            <div className="review-side-column">
              <ReviewSuggestions review={review} />
              <ReviewFindings review={review} />
              <HandoffPanel key={`${state.saved.version.source_revision_id}.${state.saved.version.decision_version}.${state.saved.status}`} review={review} session={session} />
              <FindingDiscussion key={state.saved.version.source_revision_id} review={review} session={session} />
              {review.canEdit && <ReviewSettings review={review} csrf={session.csrf_token} />}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
