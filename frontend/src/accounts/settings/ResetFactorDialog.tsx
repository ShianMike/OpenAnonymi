import { useState } from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { resetMemberSecondFactor, type MemberView } from '../../api/client'
import { InlineNotice } from '../../ui/WorkspaceControls'

export function ResetFactorDialog({ member, workspaceId, csrfToken, onReset }: {
  member: MemberView; workspaceId: string; csrfToken: string; onReset: () => void;
}) {
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function reset() {
    setPending(true); setError(null)
    try { await resetMemberSecondFactor(workspaceId, member.user_id, csrfToken); setOpen(false); onReset() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The authenticator could not be reset.') }
    finally { setPending(false) }
  }
  return (
    <div className="member-access-section">
      <h3>Lost authenticator</h3>
      <p>A reset signs this member out everywhere and requires a new authenticator at their next sign-in. You must administer all of their active workspaces.</p>
      <AlertDialog.Root open={open} onOpenChange={(value) => { if (!pending) { setOpen(value); setError(null) } }}>
        <AlertDialog.Trigger className="quiet-button">Reset authenticator</AlertDialog.Trigger>
        <AlertDialog.Portal><AlertDialog.Overlay className="workspace-dialog-overlay" />
          <AlertDialog.Content className="workspace-dialog" onEscapeKeyDown={(event) => { if (pending) event.preventDefault() }}>
            <AlertDialog.Title>Reset this authenticator?</AlertDialog.Title>
            <AlertDialog.Description>{member.email} will lose all sessions and backup codes and must set up an authenticator before continuing.</AlertDialog.Description>
            {error && <InlineNotice error>{error}</InlineNotice>}
            <div className="dialog-actions"><AlertDialog.Cancel disabled={pending}>Cancel</AlertDialog.Cancel><button type="button" disabled={pending} onClick={() => void reset()}>{pending ? 'Resetting…' : 'Confirm authenticator reset'}</button></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </div>
  )
}
