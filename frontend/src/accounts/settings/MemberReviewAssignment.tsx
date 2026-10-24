import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ChevronRight, Search } from 'lucide-react'
import { ApiRequestError, getWorkspaceDocuments, type DocumentIndexView, type MemberView } from '../../api/client'
import { getHandoff, saveHandoff, type HandoffView } from '../../team/api'
import { ChoiceSwitch, InlineNotice } from '../../ui/WorkspaceControls'
import { LoadingState } from '../../loading/LoadingState'
import { documentLabel, documentStatuses } from '../../workspace/documents/documentPresentation'
import { assignableReviews } from './memberPresentation'

type Props = {
  member: MemberView; workspaceId: string; csrfToken: string; onBack: () => void
  onBusyChange: (busy: boolean) => void; onAssigned: (message: string) => void; onRequestFailed: (cause: unknown) => void
}

export function MemberReviewAssignment({ workspaceId, onRequestFailed, ...props }: Props) {
  const [items, setItems] = useState<DocumentIndexView[] | null>(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<DocumentIndexView | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [now, setNow] = useState(Date.now)
  const searchInput = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    getWorkspaceDocuments(workspaceId, controller.signal)
      .then(value => { if (!controller.signal.aborted) setItems(value) })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Reviews could not be loaded.'); onRequestFailed(cause) } })
    return () => controller.abort()
  }, [workspaceId, onRequestFailed, attempt])
  if (selected) return <ReviewAssignmentForm key={selected.id} {...props} workspaceId={workspaceId} onRequestFailed={onRequestFailed} document={selected} onBack={() => {
    setSelected(null); requestAnimationFrame(() => searchInput.current?.focus())
  }} />
  const reviews = assignableReviews(items ?? [], search, now)
  return <>
    <div className="people-dialog-body people-assignment">
      <p className="people-assignment-recipient">Choose a review for <strong>{props.member.email}</strong>.</p>
      <p className="people-assignment-help">Only reviews you own are available. Expired reviews and reviews with a scan in progress are excluded.</p>
      <label className="people-search"><Search size={15} aria-hidden="true" /><input ref={searchInput} autoFocus type="search" aria-label="Search your reviews" placeholder="Search your reviews…" value={search} onChange={event => setSearch(event.target.value)} maxLength={200} /></label>
      {error ? <InlineNotice error title="Reviews couldn’t be loaded" actions={<button type="button" className="people-button" onClick={() => { setError(''); setItems(null); setAttempt(value => value + 1) }}>Retry reviews</button>}>{error}</InlineNotice>
        : items === null ? <LoadingState label="Loading your reviews…" compact />
          : reviews.length ? <ul className="people-review-list">{reviews.map(item => <li key={item.id}><button type="button" onClick={() => setSelected(item)}>
            <span><strong>{documentLabel(item)}</strong><small>{documentStatuses.find(status => status.value === item.status)?.label} · Updated {new Date(item.updated_at).toLocaleDateString()}</small></span><ChevronRight size={16} aria-hidden="true" />
          </button></li>)}</ul>
            : <div className="people-assignment-empty"><h3>{search.trim() ? 'No matching reviews' : 'No reviews to assign'}</h3><p>{search.trim() ? 'Try a different title.' : 'Create a review in this workspace, then return here to assign it.'}</p></div>}
    </div>
    <footer className="people-dialog-footer"><div><button type="button" className="people-button people-dialog-back" onClick={props.onBack}><ArrowLeft size={14} aria-hidden="true" />Back</button></div></footer>
  </>
}

export function ReviewAssignmentDetails({ member, handoff }: { member: MemberView; handoff: HandoffView }) {
  return <div className="people-assignment-permissions"><h3>Reviewer access</h3><p><strong>{member.email}</strong> can read original content, make decisions, comment and approve this review. You control source edits and exports.</p>
    {handoff.reviewer_id && handoff.reviewer_id !== member.user_id && <p className="people-assignment-replace">This replaces {handoff.reviewer_email ?? 'the current reviewer'}’s access to this review.</p>}
  </div>
}

function ReviewAssignmentForm({ document, member, csrfToken, onBack, onBusyChange, onAssigned, onRequestFailed }: Props & { document: DocumentIndexView }) {
  const [handoff, setHandoff] = useState<HandoffView | null>(null)
  const [required, setRequired] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const backButton = useRef<HTMLButtonElement>(null)
  useEffect(() => { backButton.current?.focus() }, [])
  useEffect(() => {
    const controller = new AbortController()
    getHandoff(document.id, controller.signal).then(value => {
      if (controller.signal.aborted) return
      if (!value.is_owner) { setError('Only the document owner can assign a reviewer.'); return }
      setHandoff(value); setRequired(value.require_approval)
    }).catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Review access could not be loaded.'); onRequestFailed(cause) } })
    return () => controller.abort()
  }, [document.id, attempt, onRequestFailed])
  const policyRequired = handoff?.approval_policy === 'always'
  const requireApproval = policyRequired || required
  const changed = handoff && (handoff.reviewer_id !== member.user_id || handoff.require_approval !== requireApproval)
  return <form className="people-dialog-form" onSubmit={async event => {
    event.preventDefault()
    if (!handoff || !changed || pending || member.revoked_at || member.disabled_at) return
    setPending(true); onBusyChange(true); setError('')
    try {
      await saveHandoff(document.id, handoff.version, member.user_id, requireApproval, csrfToken)
      onAssigned(`${documentLabel(document)} assigned to ${member.email}.${requireApproval ? ' Reviewer approval is required before export.' : ''}`)
    } catch (cause) {
      setError(cause instanceof ApiRequestError && cause.status === 409 ? 'This review changed. Reload its current access, check the details, then assign again.'
        : cause instanceof Error ? cause.message : 'The reviewer could not be assigned.')
      setHandoff(null); onRequestFailed(cause)
    } finally { setPending(false); onBusyChange(false) }
  }}>
    <div className="people-dialog-body people-assignment">
      <div className="people-selected-review"><span>Selected review</span><h3>{documentLabel(document)}</h3></div>
      {handoff && <>
        <ReviewAssignmentDetails member={member} handoff={handoff} />
        <ChoiceSwitch label="Require approval before export" description={policyRequired ? 'Required by workspace policy for every copy and download.' : 'Copying and downloading wait until this reviewer approves the confirmed version.'}
          checked={requireApproval} disabled={pending || policyRequired} disabledReason={policyRequired ? 'Required by workspace policy.' : undefined} onChange={setRequired} />
        <p className="people-assignment-help">{changed ? 'Saving resets the review’s confirmation and any previous approval.' : 'This person is already assigned with these settings.'}</p>
      </>}
      {!handoff && !error && <LoadingState label="Checking current review access…" compact />}
      {error && <InlineNotice error title="Check review access" actions={!handoff && <button type="button" className="people-button" disabled={pending} onClick={() => { setError(''); setAttempt(value => value + 1) }}>Reload review</button>}>{error}</InlineNotice>}
    </div>
    <footer className="people-dialog-footer"><div><button ref={backButton} type="button" className="people-button people-dialog-back" disabled={pending} onClick={onBack}><ArrowLeft size={14} aria-hidden="true" />Choose another</button><button type="submit" className="people-button people-primary" disabled={pending || !changed}>{pending ? 'Assigning…' : changed ? 'Assign review' : handoff ? 'Already assigned' : 'Assign review'}</button></div></footer>
  </form>
}
