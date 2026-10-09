import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { ArrowUpRight, ChevronDown, ShieldCheck, UserMinus, UserRoundCheck } from 'lucide-react'
import { changeMemberRole, restoreMember, revokeMember, type MemberView } from '../../api/client'
import { DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'
import { ResetFactorDialog } from './ResetFactorDialog'

export function MemberDialog({
  member,
  workspaceId,
  workspaceName,
  csrfToken,
  onChanged,
}: {
  member: MemberView
  workspaceId: string
  workspaceName: string
  csrfToken: string
  onChanged: (value: MemberView) => void
}) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [role, setRole] = useState(member.role)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const revoked = member.revoked_at !== null
  const initials = member.email.split('@')[0].split(/[._+-]/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase()
  const roleFormId = `member-role-${member.user_id}`
  async function run(action: () => Promise<MemberView>) {
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const updated = await action()
      onChanged(updated)
      setConfirm(false)
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Membership could not be updated.')
    } finally {
      setPending(false)
    }
  }
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!pending) {
          setOpen(value)
          setRole(member.role)
          setError(null)
        }
      }}
    >
      <Dialog.Trigger asChild>
        <button className="quiet-button member-manage" aria-label={`Manage ${member.email}`} type="button">
          Manage <ArrowUpRight size={15} aria-hidden="true" />
        </button>
      </Dialog.Trigger>
      <DialogFrame className="member-dialog" title="Manage membership" description={`Access and role in ${workspaceName}.`} busy={pending}>
        <div className="member-dialog-identity">
          <span className="member-avatar" aria-hidden="true">{initials}</span>
          <div><strong>{member.email}</strong><span>{member.disabled_at ? 'Account disabled' : revoked ? 'Access revoked' : 'Active member'}</span></div>
        </div>
        {!revoked && (
          <form
            id={roleFormId}
            onSubmit={(event) => {
              event.preventDefault()
              void run(() => changeMemberRole(workspaceId, member.user_id, role, csrfToken))
            }}
          >
            <fieldset className="member-role-options" disabled={pending}>
              <legend>Workspace role</legend>
              <label><input type="radio" aria-label="Member" name={roleFormId} value="member" checked={role === 'member'} onChange={() => setRole('member')} />
                <span><UserRoundCheck size={19} aria-hidden="true" /><strong>Member</strong><small>Review their documents and reviews shared with them.</small></span>
              </label>
              <label><input type="radio" aria-label="Administrator" name={roleFormId} value="administrator" checked={role === 'administrator'} onChange={() => setRole('administrator')} />
                <span><ShieldCheck size={19} aria-hidden="true" /><strong>Administrator</strong><small>Also manage members, rules, and retention.</small></span>
              </label>
            </fieldset>
            <p className="member-role-note">Document access follows ownership and review assignments for both roles.</p>
            {!confirm && error && <InlineNotice error>{error}</InlineNotice>}
          </form>
        )}
        {revoked ? (
          <div className="member-access-section">
            <UserRoundCheck size={21} aria-hidden="true" />
            <h3>Access is revoked</h3>
            <p>Restore membership so this person can sign in again.</p>
            {error && <InlineNotice error>{error}</InlineNotice>}
            <button
              type="button"
              disabled={pending || !!member.disabled_at}
              onClick={() => void run(() => restoreMember(workspaceId, member.user_id, csrfToken))}
            >
              Restore membership
            </button>
          </div>
        ) : (
          <details className="member-advanced-actions">
            <summary><span><ShieldCheck size={17} aria-hidden="true" />Access and recovery</span><ChevronDown size={16} aria-hidden="true" /></summary>
          <div className="member-access-section">
            <h3>Revoke workspace access</h3>
            <p>Ends active sessions. Saved reviews are retained, and access can be restored later.</p>
            <AlertDialog.Root
              open={confirm}
              onOpenChange={(value) => {
                if (!pending) {
                  setConfirm(value)
                  setError(null)
                }
              }}
            >
              <AlertDialog.Trigger className="member-revoke-button">
                <UserMinus size={15} aria-hidden="true" /> Revoke access
              </AlertDialog.Trigger>
              <AlertDialog.Portal>
                <AlertDialog.Overlay className="workspace-dialog-overlay" />
                <AlertDialog.Content
                  className="workspace-dialog"
                  onEscapeKeyDown={(event) => {
                    if (pending) event.preventDefault()
                  }}
                >
                  <AlertDialog.Title>Revoke access?</AlertDialog.Title>
                  <AlertDialog.Description>
                    {member.email} will lose access and their active sessions will end. An administrator can
                    restore membership later.
                  </AlertDialog.Description>
                  {error && <InlineNotice error>{error}</InlineNotice>}
                  <div className="dialog-actions">
                    <AlertDialog.Cancel disabled={pending}>Keep access</AlertDialog.Cancel>
                    <button
                      className="member-revoke-button"
                      type="button"
                      disabled={pending}
                      onClick={() => void run(() => revokeMember(workspaceId, member.user_id, csrfToken))}
                    >
                      {pending ? 'Revoking…' : 'Confirm revoke'}
                    </button>
                  </div>
                </AlertDialog.Content>
              </AlertDialog.Portal>
            </AlertDialog.Root>
          </div>
          {!member.disabled_at && <ResetFactorDialog member={member} workspaceId={workspaceId} csrfToken={csrfToken}
            onReset={() => { setOpen(false); onChanged(member) }} />}
          </details>
        )}
        <div className="dialog-actions">
          <Dialog.Close asChild><button type="button" className="quiet-button" disabled={pending}>{role === member.role ? 'Done' : 'Cancel'}</button></Dialog.Close>
          {!revoked && <button type="submit" form={roleFormId} disabled={pending || role === member.role}>{pending ? 'Saving…' : 'Save role'}</button>}
        </div>
      </DialogFrame>
    </Dialog.Root>
  )
}
