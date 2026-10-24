import { Link, useLocation } from 'react-router-dom'
import { ChevronLeft, ArrowUpRight, Check, FileText, Fingerprint, Circle, X } from 'lucide-react'
import type { SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { UnsavedNavigationPrompt } from '../ui/UnsavedNavigationPrompt'
import { useReviewController } from './useReviewController'
import { ReviewSuggestions } from './ReviewSuggestions'
import { ReviewDocument } from './ReviewDocument'
import { ReviewFindings } from './ReviewFindings'
import { ReviewCompletion } from './ReviewCompletion'
import { ReviewSettings } from './ReviewSettings'
import { AutosaveStatus } from '../recovery/AutosaveStatus'
import { ReviewCollaboration } from '../team/ReviewCollaboration'
import { ReviewerSteps } from '../team/ReviewerSteps'
import { StudioTheme } from './studio/StudioTheme'
import { QuickGuideButton } from '../onboarding/QuickGuide'
import './review-workspace.css'

export function EditDraftPage({ session, onUnsavedChange }: {
  session: SessionView; onUnsavedChange?: (dirty: boolean) => void
}) {
  const review = useReviewController(session)
  const location = useLocation()
  const { state, dirty, settingsDirty, pendingFindings, lastFocusedRef } = review
  const workspaceId = state.kind === 'ready' ? state.saved.workspace_id : location.state?.workspaceId
  const returnSearch = new URLSearchParams(typeof location.state?.documentsSearch === 'string' ? location.state.documentsSearch : '')
  if (workspaceId) returnSearch.set('workspace', workspaceId)
  const backTo = `/documents${returnSearch.size ? `?${returnSearch}` : ''}`
  const total = review.activeFindings.length
  const decided = total - pendingFindings.length
  return <section className="studio review-studio" aria-labelledby="review-title" onFocusCapture={event => {
    if (event.target instanceof HTMLElement) lastFocusedRef.current = event.target
  }}>
    <header className="studio-topbar">
      <Link className="studio-back" to={backTo} aria-label="Back to documents"><ChevronLeft size={18} aria-hidden="true" /><span>Documents</span></Link>
      <Fingerprint className="studio-brand" size={24} aria-label="OpenAnonymi" />
      <div className="studio-title"><h1 id="review-title">{state.kind === 'ready' ? state.saved.title || 'Untitled review' : state.kind === 'loading' ? 'Opening review' : 'Review unavailable'}</h1>
        <span>{session.memberships.find(item => item.workspace_id === workspaceId)?.workspace_name ?? 'Review workspace'}<span className="studio-title-separator">/</span>
          {state.kind === 'loading' ? 'Loading…' : state.kind === 'error' ? 'Unavailable' : dirty || settingsDirty ? 'Unsaved changes' : review.decisionPending ? 'Saving…' : 'All changes saved'}</span>
      </div>
      <div className="studio-header-actions">
        <QuickGuideButton />
        <StudioTheme />
        {state.kind === 'ready' && <>
          <ReviewCollaboration key={state.saved.version.document_id} review={review} session={session} />
          {review.canEdit && <ReviewSettings review={review} csrf={session.csrf_token} />}
          <ReviewCompletion review={review} />
        </>}
      </div>
    </header>
    <UnsavedNavigationPrompt when={review.decisionPending || ((dirty || settingsDirty) && !review.recovery.protected)}
      saving={review.decisionPending} onWaitAndLeave={review.flushDecisions}
      focusBackId={dirty ? 'saved-source' : 'review-suggestion-settings'} onDirtyChange={onUnsavedChange}
      onSaveAndLeave={review.recovery.flush} onDiscardAndLeave={review.recovery.clear}
      onStay={() => {
        if (dirty) { review.setMobilePanel('original'); review.setEditingSource(true) }
        else if (settingsDirty) review.setSettingsOpen(true)
      }} />
    {state.kind === 'loading' && <LoadingState label="Opening your review…" shape="document" onRetry={review.reloadSaved} />}
    {state.kind === 'error' && <div className="studio-message" role="alert"><p>{state.message}</p>
      {state.retryable !== false && <button type="button" onClick={review.reloadSaved}>Retry</button>}</div>}
    {state.kind === 'ready' && <>
      <ReviewerSteps review={review} />
      {(review.error || review.conflict) && !dirty && <div className="studio-notice is-error" role="alert"><span>{review.error || 'A newer version is saved. Reload it to continue.'}</span>
        {review.conflict && <button type="button" onClick={review.reloadSaved}>Reload latest review</button>}</div>}
      <div className="studio-workbench" data-mobile-panel={review.mobilePanel}>
        <ReviewDocument review={review} userId={session.user_id} />
        <aside className="studio-inspector" aria-label="Review findings">
          <div className="inspector-heading"><h2>Findings <span>{total}</span></h2>
            <button type="button" className="studio-icon" aria-label="Show original document" onClick={() => review.setMobilePanel('original')}><FileText size={17} /></button>
          </div>
          <ReviewSuggestions review={review} />
          <ReviewFindings review={review} />
          {total > 0 && <div className="inspector-next"><div><strong>{pendingFindings.length ? `${pendingFindings.length} left to review` : 'Every finding reviewed'}</strong><span>Then read the full output.</span></div>
            <button type="button" className="studio-icon" aria-label="Read reviewed output" onClick={() => review.setMobilePanel('preview')}><ArrowUpRight size={20} /></button></div>}
        </aside>
      </div>
      <footer className="studio-statusbar"><span><Circle size={7} fill="currentColor" />{review.scan?.status === 'completed' ? `${decided} of ${total} findings reviewed` : review.scan?.status === 'scanning' ? 'Checking your document…' : 'Ready to scan'}</span>
        <span className="studio-status-count">{Array.from(state.saved.text).length.toLocaleString()} characters</span>
        {review.canEdit && <AutosaveStatus recovery={review.recovery} dirty={dirty || settingsDirty} />}
      </footer>
      {review.notice && <div className="studio-toast" role="status" aria-atomic="true"><Check size={16} aria-hidden="true" /><span>{review.notice}</span>
        <button type="button" className="studio-icon" aria-label="Dismiss notification" onClick={() => review.setNotice(null)}><X size={15} /></button></div>}
    </>}
  </section>
}
