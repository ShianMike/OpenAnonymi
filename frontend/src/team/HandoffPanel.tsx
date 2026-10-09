import { LoadingState } from '../loading/LoadingState'
import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { CheckCircle2, UserRoundCheck, UsersRound } from 'lucide-react'
import { ApiConflictError, type SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { DialogFrame, ChoiceSwitch, InlineNotice, PanelHeading } from '../ui/WorkspaceControls'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { GlassSelect } from '../ui/GlassSelect'
import { readReviewedOutput } from './reviewerNavigation'
import { approveReview, getTeammates, saveHandoff, type TeammateView } from './api'
import './team.css'

export function HandoffPanel({ review, session }: { review: ReviewController; session: SessionView }) {
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const [open, setOpen] = useState(false)
  const [members, setMembers] = useState<TeammateView[] | null>(null)
  const [reviewer, setReviewer] = useState('')
  const [required, setRequired] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const handoff = review.handoff.value
  const documentId = saved?.version.document_id
  useEffect(() => {
    if (!open || !documentId) return
    const controller = new AbortController()
    getTeammates(documentId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setMembers(value) })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Teammates could not be loaded.') })
    return () => controller.abort()
  }, [open, documentId])
  if (!saved) return null
  const blocked = review.actionPending || review.dirty || review.settingsDirty || review.conflict || review.scan?.status === 'scanning' || pending
  const completed = ['ready', 'exported'].includes(saved.status)
  async function save(revoke = false) {
    if (!saved) return
    setPending(true); setError(null)
    try {
      await saveHandoff(saved.version.document_id, saved.version, revoke ? null : reviewer || null,
        handoff?.approval_policy === 'always' || required, session.csrf_token)
      setOpen(false); await review.reloadSaved()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Handoff could not be saved.'); if (cause instanceof ApiConflictError) void review.reloadSaved() }
    finally { setPending(false) }
  }
  return <section id="review-handoff" tabIndex={-1} className="team-panel workspace-panel" aria-label="Team review handoff">
    <div className="team-heading"><PanelHeading icon={saved.can_edit ? UsersRound : UserRoundCheck} title={saved.can_edit ? 'Team review' : 'Assigned to you'}
      description={saved.can_edit ? 'Ask a teammate for a second look.' : 'Read the text, make choices and discuss details.'} />
      {saved.can_edit && handoff && <span className="team-policy">{handoff.require_approval ? 'Required' : 'Optional'}</span>}
    </div>
    {review.handoff.error && <InlineNotice error>{review.handoff.error}<button type="button" onClick={review.handoff.retry}>Retry handoff</button></InlineNotice>}
    {!handoff && !review.handoff.error && <p role="status" className="field-note">Checking review access…</p>}
    {handoff && <>
      {saved.can_edit && handoff.reviewer_id && <p className="team-assignee">{handoff.reviewer_email ?? 'Assigned reviewer'}
        {handoff.reviewer_id && !handoff.reviewer_active && <span className="field-note">Access no longer active</span>}
      </p>}
      <p className="field-note">{handoff.require_approval ? saved.can_edit ? 'A teammate must approve this version before you can copy or download it.' : 'Your approval is required before the owner can copy or download.' : saved.can_edit ? handoff.reviewer_id ? 'You can share after confirming; teammate approval is optional.' : 'You can finish this review yourself, or invite a teammate to check it.' : 'Your approval is optional. The owner handles copying and downloading.'}</p>
      {handoff.approved_at && <p className="team-approved" role="status"><CheckCircle2 size={16} aria-hidden="true" /> This exact version is independently approved.</p>}
      {saved.can_edit ? <Dialog.Root open={open} onOpenChange={(next) => {
        if (pending) return
        if (next) { setReviewer(handoff.reviewer_id ?? ''); setRequired(handoff.require_approval); setMembers(null); setError(null) }
        setOpen(next)
      }}>
        <Dialog.Trigger asChild><button type="button" disabled={blocked}>Manage reviewer</button></Dialog.Trigger>
        <DialogFrame title="Ask a teammate to review" description="This teammate can read the original private text, make choices, comment and approve. You control text edits, deletion, copying and downloading." busy={pending}>
          {members === null && !error && <LoadingState label="Loading active teammates…" compact />}
          {members && <form onSubmit={(event) => { event.preventDefault(); void save() }} className="team-form">
            <label htmlFor="review-teammate">Reviewer</label>
            <GlassSelect id="review-teammate" value={reviewer} onValueChange={setReviewer} disabled={pending}>
              <option value="">No reviewer · Remove access</option>
              {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.email}</option>)}
            </GlassSelect>
            {members.length === 0 && <p className="field-note">No active teammates available. An administrator can add members in Settings.</p>}
            <ChoiceSwitch label="Require teammate approval" description={handoff.approval_policy === 'always'
              ? 'Your workspace requires a teammate’s approval for every copy and download.'
              : 'Copying and downloading stay locked until this teammate approves the confirmed version.'}
              checked={handoff.approval_policy === 'always' || required}
              disabled={pending || handoff.approval_policy === 'always'} onChange={setRequired} />
            <p className="field-note">Changing these options resets confirmation and approval. If approval is required, removing the reviewer keeps sharing locked until you assign someone else{handoff.approval_policy === 'always' ? '.' : ' or turn off required approval.'}</p>
            <button type="submit" disabled={pending}>{pending ? 'Saving…' : reviewer ? 'Grant review access' : 'Save review access'}</button>
          </form>}
          {error && <InlineNotice error>{error}</InlineNotice>}
        </DialogFrame>
      </Dialog.Root> : <>
        <button className="team-read-output" type="button" disabled={blocked} onClick={() => readReviewedOutput(review)}>Read reviewed output</button>
        {!completed && <p className="field-note">The owner must confirm the complete reviewed output before you can approve it.</p>}
        {completed && !handoff.approved_at && <div className="team-approval">
          <GlassCheckbox id="second-approve" label="I read the full reviewed output and approve this version." checked={confirmed} disabled={blocked} onCheckedChange={setConfirmed} />
          <button type="button" disabled={blocked || !confirmed} onClick={async () => {
            setPending(true); setError(null)
            try { await approveReview(saved.version.document_id, saved.version, session.csrf_token); setConfirmed(false); review.handoff.retry() }
            catch (cause) { setError(cause instanceof Error ? cause.message : 'Approval could not be saved.') }
            finally { setPending(false) }
          }}>{pending ? 'Approving…' : 'Approve this version'}</button>
        </div>}
      </>}
      {error && !open && <InlineNotice error>{error}</InlineNotice>}
    </>}
  </section>
}
