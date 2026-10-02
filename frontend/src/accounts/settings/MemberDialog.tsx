import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { ArrowUpRight, UserMinus, UserRoundCheck } from 'lucide-react'
import { changeMemberRole, restoreMember, revokeMember, type MemberView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'

export function MemberDialog({
  member,
  workspaceId,
  csrfToken,
  onChanged,
}: {
  member: MemberView
  workspaceId: string
  csrfToken: string
  onChanged: (value: MemberView) => void
}) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [role, setRole] = useState(member.role)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const revoked = member.revoked_at !== null
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
      <DialogFrame title="Manage membership" description={member.email} busy={pending}>
        {!revoked && (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void run(() => changeMemberRole(workspaceId, member.user_id, role, csrfToken))
            }}
          >
            <div>
              <label className="field-label" htmlFor={`role-${member.user_id}`}>
                Workspace role
              </label>
              <GlassSelect
                id={`role-${member.user_id}`}
                value={role}
                onValueChange={(value) => setRole(value as MemberView['role'])}
                disabled={pending}
              >
                <option value="member" data-description="Review and export their own documents.">
                  Member
                </option>
                <option value="administrator" data-description="Manage members, rules and retention.">
                  Administrator
                </option>
              </GlassSelect>
            </div>
            {!confirm && error && <InlineNotice error>{error}</InlineNotice>}
            <div className="dialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="quiet-button" disabled={pending}>
                  Cancel
                </button>
              </Dialog.Close>
              <button type="submit" disabled={pending || role === member.role}>
                {pending ? 'Saving…' : 'Save role'}
              </button>
            </div>
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
        )}
      </DialogFrame>
    </Dialog.Root>
  )
}
