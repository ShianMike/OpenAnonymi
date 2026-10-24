import { useId, useRef, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowLeft } from 'lucide-react'
import { changeMemberRole, restoreMember, revokeMember, resetMemberSecondFactor, type MemberView } from '../../api/client'
import { DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'
import { MemberRoleOptions } from './MemberRoleOptions'
import { MemberReviewAssignment } from './MemberReviewAssignment'
import { memberInitials, memberRoles, memberStatus, memberStatusLabel } from './memberPresentation'

type MemberAction = 'revoke' | 'restore' | 'reset'
const actionTitles = { revoke: 'Revoke workspace access?', restore: 'Restore workspace access?', reset: 'Reset authenticator?' }
const actionLabels = { revoke: 'Confirm revoke', restore: 'Confirm restore', reset: 'Confirm reset' }

export function MemberActionReview({ action, member, workspaceName }: { action: MemberAction; member: MemberView; workspaceName: string }) {
  const effects = {
    revoke: [
      `Access to ${workspaceName} ends immediately.`,
      'All active sessions are ended, and review assignments in this workspace are revoked.',
      'Saved reviews follow their existing retention. Membership can be restored later, but a new sign-in is required.',
    ],
    restore: [
      `${memberRoles[member.role].label} access to ${workspaceName} is restored.`,
      'They must sign in again. Previously ended sessions stay ended.',
      'Previous reviewer assignments are not restored automatically.',
    ],
    reset: [
      'All active sessions and backup codes are invalidated.',
      'They must set up a new authenticator before continuing at their next sign-in.',
      'You must administer every workspace where this person has active membership. Otherwise, the system operator must perform this reset.',
    ],
  }
  return <div className="people-action-review"><p>This change applies to <strong>{member.email}</strong>.</p><h3>What will change</h3><ul>{effects[action].map(effect => <li key={effect}>{effect}</li>)}</ul>
    {action === 'restore' && member.disabled_at && <p className="people-blocked-note">This account is disabled. Restoring workspace membership cannot enable sign-in.</p>}
  </div>
}

export function MemberDialog({ member, workspaceId, workspaceName, csrfToken, self, trigger, onChanged, onRequestFailed }: {
  member: MemberView; workspaceId: string; workspaceName: string; csrfToken: string; self: boolean; trigger: ReactNode
  onChanged: (value: MemberView, message: string) => void; onRequestFailed: (cause: unknown) => void
}) {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<'profile' | 'assign' | MemberAction>('profile')
  const [role, setRole] = useState(member.role)
  const [pending, setPending] = useState<'role' | MemberAction | null>(null)
  const [assigning, setAssigning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const backButton = useRef<HTMLButtonElement>(null)
  const accessButton = useRef<HTMLButtonElement>(null)
  const recoveryButton = useRef<HTMLButtonElement>(null)
  const assignmentButton = useRef<HTMLButtonElement>(null)
  const roleForm = useId()
  const revoked = member.revoked_at !== null
  const busy = !!pending || assigning
  function review(action: MemberAction) { setError(null); setView(action); requestAnimationFrame(() => backButton.current?.focus()) }
  function back() { const previous = view; setView('profile'); setError(null); requestAnimationFrame(() => (previous === 'assign' ? assignmentButton : previous === 'reset' ? recoveryButton : accessButton).current?.focus()) }
  async function run(action: 'role' | MemberAction) {
    if (pending || self || (action === 'role' && (revoked || role === member.role)) || (action === 'restore' && !!member.disabled_at) || (action === 'reset' && (revoked || !!member.disabled_at))) return
    setPending(action); setError(null)
    try {
      let updated = member
      if (action === 'role') updated = await changeMemberRole(workspaceId, member.user_id, role, csrfToken)
      else if (action === 'revoke') updated = await revokeMember(workspaceId, member.user_id, csrfToken)
      else if (action === 'restore') updated = await restoreMember(workspaceId, member.user_id, csrfToken)
      else await resetMemberSecondFactor(workspaceId, member.user_id, csrfToken)
      const message = action === 'role' ? `Role for ${member.email} updated to ${memberRoles[updated.role].label}.`
        : action === 'revoke' ? `Workspace access revoked for ${member.email}. Active sessions were ended.`
          : action === 'restore' ? `Workspace access restored for ${member.email}. They need to sign in again.`
            : `Authenticator reset for ${member.email}. New enrollment is required at sign-in.`
      onChanged(updated, message); setOpen(false); setView('profile')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Membership could not be updated.')
      onRequestFailed(cause)
    } finally { setPending(null) }
  }
  return <Dialog.Root open={open} onOpenChange={value => { if (!busy) { setOpen(value); setView('profile'); setRole(member.role); setError(null) } }}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <DialogFrame className="workspace-side-dialog members-dialog" title={view === 'profile' ? self ? 'Your membership' : 'Member details' : view === 'assign' ? 'Assign a review' : actionTitles[view]} description={`Workspace: ${workspaceName}.`} busy={busy}>
      {view === 'assign' ? <MemberReviewAssignment member={member} workspaceId={workspaceId} csrfToken={csrfToken} onBack={back} onBusyChange={setAssigning} onRequestFailed={onRequestFailed} onAssigned={message => { onChanged(member, message); setOpen(false); setView('profile') }} /> : <>
      <div className="people-dialog-body">
        {view !== 'profile' ? <MemberActionReview action={view} member={member} workspaceName={workspaceName} /> : <>
          <div className="people-profile"><span className="people-avatar" aria-hidden="true">{memberInitials(member.email)}</span><div><strong>{member.email}{self && <span className="people-you">You</span>}</strong><span className={`people-access is-${memberStatus(member)}`}><i aria-hidden="true" />{memberStatusLabel[memberStatus(member)]}</span></div></div>
          {self ? <div className="people-self-role"><h3>Workspace role</h3><strong>{memberRoles[member.role].label}</strong><p>{memberRoles.member.description}{member.role === 'administrator' && ` ${memberRoles.administrator.description}`}</p><p>Another administrator must change your role or revoke your access. The last active administrator cannot be removed.</p></div>
            : !revoked ? <form id={roleForm} className="people-role-form" onSubmit={event => { event.preventDefault(); void run('role') }}><MemberRoleOptions value={role} onChange={setRole} disabled={!!pending} /></form>
              : <div className="people-current-role"><span>Role when restored</span><strong>{memberRoles[member.role].label}</strong></div>}
          <p className="people-document-note">Document access follows ownership and reviewer assignments for both roles.</p>
          {!self && <>
            {!revoked && !member.disabled_at && <section className="people-access-section"><h3>Review assignment</h3><p>Give this person access to a review you own. Each review has one assigned reviewer.</p><button ref={assignmentButton} type="button" className="people-button" disabled={!!pending || role !== member.role} onClick={() => setView('assign')}>Assign a review</button>{role !== member.role && <p>Save or cancel your role change before assigning a review.</p>}</section>}
            <section className="people-access-section"><h3>Workspace access</h3>
              {member.disabled_at ? <p>This account was disabled <time dateTime={member.disabled_at}>{new Date(member.disabled_at).toLocaleString()}</time>. Workspace membership changes cannot enable sign-in.</p>
                : revoked ? <p>Access was revoked <time dateTime={member.revoked_at!}>{new Date(member.revoked_at!).toLocaleString()}</time>. You can review and restore this membership.</p>
                  : <p>This membership is enabled. Revoking it ends active sessions and removes reviewer assignments in this workspace.</p>}
              <button ref={accessButton} type="button" className={`people-button${revoked ? '' : ' people-danger'}`} disabled={!!pending || (revoked && !!member.disabled_at)} onClick={() => review(revoked ? 'restore' : 'revoke')}>{revoked ? 'Restore access' : 'Revoke access'}</button>
            </section>
            {!revoked && !member.disabled_at && <section className="people-access-section"><h3>Sign-in recovery</h3><p>Use a reset when they’ve lost their authenticator. Review the session and enrollment changes first.</p><button ref={recoveryButton} type="button" className="people-button" disabled={!!pending} onClick={() => review('reset')}>Reset authenticator</button></section>}
          </>}
        </>}
      </div>
      <footer className="people-dialog-footer">
        {error && <InlineNotice error>{error}</InlineNotice>}
        {view === 'profile' && role !== member.role && !revoked && !self && <p className="people-role-change">Role change: {memberRoles[member.role].label} → <strong>{memberRoles[role].label}</strong></p>}
        <div>{view === 'profile' ? <><Dialog.Close className="people-button" disabled={!!pending}>{role !== member.role ? 'Cancel' : 'Done'}</Dialog.Close>
          {!self && !revoked && <button type="submit" form={roleForm} className="people-button people-primary" disabled={!!pending || role === member.role}>{pending === 'role' ? 'Saving…' : 'Save role'}</button>}</>
          : <><button ref={backButton} type="button" className="people-button people-dialog-back" disabled={!!pending} onClick={back}><ArrowLeft size={14} aria-hidden="true" />Back</button>
            <button type="button" className={`people-button ${view === 'restore' ? 'people-primary' : 'people-danger-confirm'}`} disabled={!!pending || (view === 'restore' && !!member.disabled_at)} onClick={() => void run(view)}>{pending ? 'Applying…' : actionLabels[view]}</button></>}
        </div>
      </footer>
      </>}
    </DialogFrame>
  </Dialog.Root>
}
