import { useState, type FormEvent } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { UserPlus } from 'lucide-react'
import { inviteMember, type MemberView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'

export function InviteDialog({
  workspaceId,
  csrfToken,
  onInvited,
}: {
  workspaceId: string
  csrfToken: string
  onInvited: (value: MemberView) => void
}) {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<MemberView['role']>('member')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function save(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const member = await inviteMember(workspaceId, email, role, csrfToken)
      onInvited(member)
      setOpen(false)
      setEmail('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Invitation could not be sent.')
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
          setError(null)
        }
      }}
    >
      <Dialog.Trigger className="button-primary">
        <UserPlus size={16} aria-hidden="true" /> Invite member
      </Dialog.Trigger>
      <DialogFrame
        title="A new face in your workspace"
        description="Send an email invitation so they can set up their account."
        busy={pending}
      >
        <form onSubmit={save}>
          <div>
            <label className="field-label" htmlFor="invite-email">
              Email address
            </label>
            <input
              id="invite-email"
              type="email"
              required
              placeholder="name@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={pending}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="invite-role">
              Role
            </label>
            <GlassSelect
              id="invite-role"
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
          {error && <InlineNotice error>{error}</InlineNotice>}
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="quiet-button" disabled={pending}>
                Cancel
              </button>
            </Dialog.Close>
            <button type="submit" disabled={pending}>
              {pending ? 'Sending…' : 'Send invitation'}
            </button>
          </div>
        </form>
      </DialogFrame>
    </Dialog.Root>
  )
}
