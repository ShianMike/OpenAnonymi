import { useId, useRef, useState, type FormEvent } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Check, UserPlus } from 'lucide-react'
import { inviteMember, type MemberView } from '../../api/client'
import { DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'
import { MemberRoleOptions } from './MemberRoleOptions'
import { MemberReviewAssignment } from './MemberReviewAssignment'

export function InviteDialog({ workspaceId, workspaceName, csrfToken, onInvited, onAssigned, onRequestFailed }: {
  workspaceId: string; workspaceName: string; csrfToken: string; onInvited: (value: MemberView) => void
  onAssigned: (message: string) => void
  onRequestFailed: (cause: unknown) => void
}) {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<MemberView['role']>('member')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invited, setInvited] = useState<MemberView | null>(null)
  const [assigning, setAssigning] = useState(false)
  const assignButton = useRef<HTMLButtonElement>(null)
  const successHeading = useRef<HTMLHeadingElement>(null)
  const id = useId()
  async function save(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true); setError(null)
    try {
      const member = await inviteMember(workspaceId, email.trim(), role, csrfToken)
      onInvited(member); setInvited(member); setEmail(''); setRole('member')
      requestAnimationFrame(() => successHeading.current?.focus())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Invitation could not be sent.')
      onRequestFailed(cause)
    } finally { setPending(false) }
  }
  return <Dialog.Root open={open} onOpenChange={value => { if (!pending) { setOpen(value); setError(null); setInvited(null); setAssigning(false) } }}>
    <Dialog.Trigger className="people-button people-primary"><UserPlus size={15} aria-hidden="true" />Invite member</Dialog.Trigger>
    <DialogFrame className="workspace-side-dialog members-dialog" title={assigning ? 'Assign a review' : invited ? 'Invitation sent' : 'Invite a member'} description={`Workspace: ${workspaceName}.`} busy={pending}>
      {invited ? assigning ? <MemberReviewAssignment member={invited} workspaceId={workspaceId} csrfToken={csrfToken} onBusyChange={setPending} onRequestFailed={onRequestFailed}
        onBack={() => { setAssigning(false); requestAnimationFrame(() => assignButton.current?.focus()) }} onAssigned={message => { onAssigned(message); setOpen(false); setInvited(null); setAssigning(false) }} />
        : <><div className="people-dialog-body people-invited"><span className="people-invited-check"><Check size={20} aria-hidden="true" /></span><h3 ref={successHeading} tabIndex={-1}>You’ve invited {invited.email}</h3><p>They’ll receive a code by email to set up their account. You can assign a review now, and it will be available when they sign in.</p><div className="people-invite-explainer"><h3>Give them a review to start with</h3><p>Choose a review you own, then confirm their access and approval settings.</p></div></div><footer className="people-dialog-footer"><div><Dialog.Close className="people-button">Done</Dialog.Close><button ref={assignButton} type="button" className="people-button people-primary" onClick={() => setAssigning(true)}>Assign a review</button></div></footer></>
        : <form onSubmit={save} className="people-dialog-form">
        <div className="people-dialog-body">
          <div className="people-field"><label htmlFor={`${id}-email`}>Email address</label><input id={`${id}-email`} autoFocus type="email" inputMode="email" autoComplete="email" autoCapitalize="none" spellCheck={false} required maxLength={320}
            placeholder="name@company.com" value={email} onChange={event => setEmail(event.target.value)} disabled={pending} aria-describedby={`${id}-email-help`} />
            <p id={`${id}-email-help`}>Use an email address that isn’t already registered.</p>
          </div>
          <MemberRoleOptions value={role} onChange={setRole} disabled={pending} />
          <p className="people-document-note">Workspace roles do not grant access to other people’s documents. Reviews follow ownership and reviewer assignments.</p>
          <div className="people-invite-explainer"><h3>What happens next</h3><p>They’ll receive an email with a one-time code to set up their new account. Workspace access is enabled when you send this invitation.</p></div>
        </div>
        <footer className="people-dialog-footer">
          {error && <InlineNotice error>{error}</InlineNotice>}
          <p>{role === 'administrator' ? 'Administrators can change workspace settings and manage other members.' : 'Members can create reviews and work on reviews assigned to them.'}</p>
          <div><Dialog.Close className="people-button" disabled={pending}>Cancel</Dialog.Close><button type="submit" className="people-button people-primary" disabled={pending || !email.trim()}>{pending ? 'Sending…' : 'Send invitation'}</button></div>
        </footer>
      </form>}
    </DialogFrame>
  </Dialog.Root>
}
