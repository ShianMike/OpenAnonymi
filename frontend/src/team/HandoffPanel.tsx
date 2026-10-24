import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ShieldCheck, Users } from 'lucide-react'
import { ApiConflictError, type SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { LoadingState } from '../loading/LoadingState'
import { ChoiceSwitch, InlineNotice } from '../ui/WorkspaceControls'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { StudioSelect } from '../review/studio/StudioControls'
import { approveReview, getTeammates, saveHandoff, type HandoffView, type TeammateView } from './api'
import './team.css'

type Props = { review: ReviewController; session: SessionView; busy: boolean; onBusyChange: (busy: boolean) => void; onSaved: () => void; onReadOutput: () => void }

export function HandoffPanel({ review, session, busy, onBusyChange, onSaved, onReadOutput }: Props) {
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const [members, setMembers] = useState<TeammateView[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [confirmed, setConfirmed] = useState(false)
  const handoff = review.handoff.value
  const documentId = saved?.version.document_id
  const owner = saved?.can_edit
  useEffect(() => {
    if (!owner || !documentId) return
    const controller = new AbortController()
    getTeammates(documentId, controller.signal)
      .then(value => { if (!controller.signal.aborted) setMembers(value) })
      .catch(cause => { if (!controller.signal.aborted) setLoadError(cause instanceof Error ? cause.message : 'Teammates could not be loaded.') })
    return () => controller.abort()
  }, [documentId, owner, attempt])
  if (!saved) return null
  const blocked = review.actionPending || review.dirty || review.settingsDirty || review.conflict || review.scan?.status === 'scanning' || busy
  const completed = ['ready', 'exported'].includes(saved.status)
  return <section id="review-handoff" className="collaboration-section" aria-label="Review access">
    {review.handoff.error && <InlineNotice error title="Review access is unavailable" actions={<button type="button" onClick={review.handoff.retry}>Retry review access</button>}>{review.handoff.error}</InlineNotice>}
    {!handoff && !review.handoff.error && <LoadingState label="Checking review access…" compact />}
    {handoff && (saved.can_edit ? <>
      {members === null && !loadError && <LoadingState label="Loading active teammates…" compact />}
      {loadError && <InlineNotice error title="Teammates couldn’t be loaded" actions={<button type="button" onClick={() => { setLoadError(''); setMembers(null); setAttempt(value => value + 1) }}>Try again</button>}>{loadError}</InlineNotice>}
      {members && <ReviewerAccessForm review={review} session={session} handoff={handoff} members={members} busy={busy} onBusyChange={onBusyChange} onSaved={onSaved} />}
    </> : <>
      <div className="collaboration-section-heading"><h3>Your review</h3><span className="collaboration-policy">{handoff.require_approval ? 'Approval required' : 'Approval optional'}</span></div>
      <p className="collaboration-description">You can review findings and discuss details. The document owner confirms and exports the finished version.</p>
      <button className="collaboration-read-output" type="button" disabled={blocked} onClick={onReadOutput}>Read reviewed output</button>
      {handoff.approved_at ? <div className="collaboration-approved" role="status"><CheckCircle2 size={18} aria-hidden="true" /><div><strong>You approved this version</strong><p>Your approval is saved for the current source, settings and decisions.</p></div></div>
        : <>
          {!completed && <p className="collaboration-note">The owner needs to confirm this version before you can approve it.</p>}
          {completed && <div className="collaboration-approval">
            <GlassCheckbox id="second-approve" label="I read the full reviewed output and approve this version." checked={confirmed} disabled={blocked} onCheckedChange={setConfirmed} />
            <button type="button" className="studio-primary" disabled={blocked || !confirmed} onClick={async () => {
              if (blocked || !confirmed) return
              onBusyChange(true); setError('')
              try { await approveReview(saved.version.document_id, saved.version, session.csrf_token); setConfirmed(false); review.handoff.retry() }
              catch (cause) { setError(cause instanceof Error ? cause.message : 'Approval could not be saved.') }
              finally { onBusyChange(false) }
            }}>{busy ? 'Approving…' : 'Approve this version'}</button>
          </div>}
        </>}
      {error && <InlineNotice error>{error}</InlineNotice>}
    </>)}
  </section>
}

export function ReviewerAccessForm({ review, session, handoff, members, busy, onBusyChange, onSaved }: Omit<Props, 'onReadOutput'> & { handoff: HandoffView; members: TeammateView[] }) {
  const [reviewer, setReviewer] = useState(handoff.reviewer_id ?? '')
  const [required, setRequired] = useState(handoff.require_approval)
  const [error, setError] = useState('')
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  const policyRequired = handoff.approval_policy === 'always'
  const requireApproval = policyRequired || required
  const changed = reviewer !== (handoff.reviewer_id ?? '') || requireApproval !== handoff.require_approval
  const validReviewer = !reviewer || members.some(member => member.user_id === reviewer)
  const blockedReason = review.conflict ? 'Reload the latest review before changing access.'
    : review.dirty || review.settingsDirty ? 'Save your document changes before changing review access.'
      : review.scan?.status === 'scanning' ? 'Wait for the current scan to finish before changing access.'
        : review.actionPending ? 'Wait for your current changes to finish saving.' : ''
  const blocked = !!blockedReason || busy
  const administrator = session.memberships.some(member => member.workspace_id === saved.workspace_id && member.role === 'administrator')
  return <form className="collaboration-access-form" onSubmit={async event => {
    event.preventDefault()
    if (blocked || !changed || !validReviewer) return
    onBusyChange(true); setError('')
    try {
      await saveHandoff(saved.version.document_id, saved.version, reviewer || null, requireApproval, session.csrf_token)
      onSaved(); await review.reloadSaved()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Review access could not be saved.'); if (cause instanceof ApiConflictError) void review.reloadSaved() }
    finally { onBusyChange(false) }
  }}>
    <div className="collaboration-section-heading"><h3>Reviewer access</h3><span className="collaboration-policy">{policyRequired ? 'Workspace policy' : requireApproval ? 'Approval required' : 'Approval optional'}</span></div>
    <p className="collaboration-description">Choose one teammate to review this document with you.</p>
    {members.length === 0 && !handoff.reviewer_id ? <div className="collaboration-empty-team"><Users size={25} strokeWidth={1.4} aria-hidden="true" /><h4>No teammates to assign</h4><p>{administrator ? 'Add a teammate to this workspace, then assign them to the review.' : 'Ask a workspace administrator to add a teammate before assigning a reviewer.'}</p>
      {administrator && <Link to={`/members?workspace=${encodeURIComponent(saved.workspace_id)}`}>Manage workspace members</Link>}
    </div> : <div className="collaboration-reviewer-field"><label htmlFor="review-teammate">Reviewer</label>
      <StudioSelect id="review-teammate" value={reviewer} onValueChange={setReviewer} disabled={blocked}>
        <option value="">No reviewer</option>
        {handoff.reviewer_id && !members.some(member => member.user_id === handoff.reviewer_id) && <option value={handoff.reviewer_id} disabled>{handoff.reviewer_email ?? 'Previous reviewer'} · Inactive</option>}
        {members.map(member => <option key={member.user_id} value={member.user_id}>{member.email}</option>)}
      </StudioSelect>
      {reviewer && !validReviewer && <p className="collaboration-note">This reviewer no longer has active workspace access. Choose another teammate or remove the assignment.</p>}
      <p className="collaboration-permissions"><ShieldCheck size={15} aria-hidden="true" /><span>The reviewer can read original text, make decisions, comment and approve. You control source edits and exports.</span></p>
    </div>}
    <ChoiceSwitch label="Require approval before export" description={policyRequired ? 'Your workspace requires independent approval for every copy and download.' : 'Copying and downloading wait until the assigned reviewer approves the confirmed version.'}
      checked={requireApproval} disabled={blocked || policyRequired || (!reviewer && !requireApproval)}
      disabledReason={policyRequired ? 'Required by workspace policy.' : !reviewer && !requireApproval ? 'Choose a reviewer before requiring approval.' : undefined} onChange={setRequired} />
    {handoff.approved_at && <p className="collaboration-approved" role="status"><CheckCircle2 size={16} aria-hidden="true" />This exact version is approved.</p>}
    {changed && <p className="collaboration-change-note">Saving resets confirmation and approval.{!reviewer && requireApproval && ' Export will stay locked until another reviewer is assigned and approves.'}</p>}
    {blockedReason && <p className="collaboration-note" role="status">{blockedReason}</p>}
    {error && <InlineNotice error>{error}</InlineNotice>}
    <footer className="collaboration-form-footer"><span>{changed ? 'Unsaved changes' : 'Up to date'}</span><button type="submit" className="studio-primary" disabled={blocked || !changed || !validReviewer}>{busy ? 'Saving…' : 'Save changes'}</button></footer>
  </form>
}
