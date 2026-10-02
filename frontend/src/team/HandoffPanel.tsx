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
      await saveHandoff(saved.version.document_id, saved.version, revoke ? null : reviewer || null, required, session.csrf_token)
      setOpen(false); await review.reloadSaved()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Handoff could not be saved.'); if (cause instanceof ApiConflictError) void review.reloadSaved() }
    finally { setPending(false) }
  }
  return <section id="review-handoff" tabIndex={-1} className="team-panel workspace-panel" aria-label="Team review handoff">
    <PanelHeading icon={saved.can_edit ? UsersRound : UserRoundCheck} title={saved.can_edit ? 'Team review' : 'Assigned to you'}
      description={saved.can_edit ? 'Another set of eyes, when you need it.' : 'Review the source, decide findings and discuss details.'} />
    {review.handoff.error && <InlineNotice error>{review.handoff.error}<button type="button" onClick={review.handoff.retry}>Retry handoff</button></InlineNotice>}
    {!handoff && !review.handoff.error && <p role="status" className="field-note">Checking review access…</p>}
    {handoff && <>
      {saved.can_edit && <p className="team-assignee">{handoff.reviewer_email ?? 'No reviewer assigned'}
        {handoff.reviewer_id && !handoff.reviewer_active && <span className="field-note">Access no longer active</span>}
      </p>}
      <p className="field-note">{handoff.require_approval ? saved.can_edit ? 'Independent approval is required before copying or downloading.' : 'Your approval is required before the owner can copy or download.' : saved.can_edit ? 'Second approval is optional.' : 'Your independent approval is optional. The owner handles exports.'}</p>
      {handoff.approved_at && <p className="team-approved" role="status"><CheckCircle2 size={16} aria-hidden="true" /> This exact version is independently approved.</p>}
      {saved.can_edit ? <Dialog.Root open={open} onOpenChange={(next) => {
        if (pending) return
        if (next) { setReviewer(handoff.reviewer_id ?? ''); setRequired(handoff.require_approval); setMembers(null); setError(null) }
        setOpen(next)
      }}>
        <Dialog.Trigger asChild><button type="button" disabled={blocked}>Manage reviewer</button></Dialog.Trigger>
        <DialogFrame title="Share this review with a teammate" description="The chosen teammate can read the protected source, decide findings, comment and approve. You control source revisions, deletion and exports." busy={pending}>
          {members === null && !error && <LoadingState label="Loading active teammates…" compact />}
          {members && <form onSubmit={(event) => { event.preventDefault(); void save() }} className="team-form">
            <label htmlFor="review-teammate">Reviewer</label>
            <GlassSelect id="review-teammate" value={reviewer} onValueChange={setReviewer} disabled={pending}>
              <option value="">No reviewer · Revoke access</option>
              {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.email}</option>)}
            </GlassSelect>
            {members.length === 0 && <p className="field-note">No active teammates available. An administrator can add members in Settings.</p>}
            <ChoiceSwitch label="Require independent approval" description="Export stays locked until the assigned teammate approves the current confirmed version." checked={required} disabled={pending} onChange={setRequired} />
            <p className="field-note">Changing the handoff invalidates the current confirmation and approval. Revoking access keeps required approval locked until you assign another reviewer or explicitly turn it off.</p>
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
