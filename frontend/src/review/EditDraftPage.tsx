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
  const workspaceId = review.state.kind === 'ready' ? review.state.saved.workspace_id
    : session.memberships.find((item) => item.workspace_id === location.state?.workspaceId)?.workspace_id
  const backTo = fromContinue ? `/continue${workspaceId ? `?workspace=${workspaceId}` : ''}` : '/documents'
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
    activeFindings,
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
        action={<Link to={backTo}>{fromContinue ? 'Back to reviews' : 'Back to documents'}</Link>}
      />
      <UnsavedNavigationPrompt
        when={(dirty || settingsDirty) && !review.recovery.protected}
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
              {scan?.status === 'completed' || activeFindings.length > 0 ? (
                <span>
                  {pendingFindings.length > 0
                    ? `${pendingFindings.length} ${pendingFindings.length === 1 ? 'finding' : 'findings'} still need a decision`
                    : state.saved.status === 'ready' || state.saved.status === 'exported'
                      ? 'Review confirmed'
                      : activeFindings.length === 0
                        ? 'No matches; review full text'
                        : 'All findings decided · Ready for a final check'}
                </span>
              ) : (
                <span>
                  {scan?.status === 'scanning' ? 'Checking suggestions' : 'Suggestion scan not run'}
                </span>
              )}
              {dirty && <span>Unsaved source edits</span>}
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
              <ReviewFindings review={review} />
              <ReviewSuggestions review={review} />
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
