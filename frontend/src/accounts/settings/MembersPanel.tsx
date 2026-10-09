import { useState } from 'react'
import { ShieldCheck, Users } from 'lucide-react'
import type { MemberView, SessionView } from '../../api/client'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import { InviteDialog } from './InviteDialog'
import { MemberDialog } from './MemberDialog'

export function MembersPanel({
  members,
  session,
  workspaceId,
  onChanged,
}: {
  members: MemberView[]
  session: SessionView
  workspaceId: string
  onChanged: (member: MemberView) => void
}) {
  const [notice, setNotice] = useState<string | null>(null)
  const activeCount = members.filter(member => !member.revoked_at && !member.disabled_at).length
  return (
    <div className="members-panel workspace-panel">
      <div className="members-panel-heading">
        <PanelHeading
          icon={Users}
          title="People in your workspace"
          description={`${activeCount} active member${activeCount === 1 ? '' : 's'} · Everyone reviews their own documents.`}
        />
        <InviteDialog
          workspaceId={workspaceId}
          csrfToken={session.csrf_token}
          onInvited={(member) => {
            onChanged(member)
            setNotice('Invitation sent. The member can set a password using the code in email.')
          }}
        />
      </div>
      {notice && <InlineNotice>{notice}</InlineNotice>}
      <div className="members-column-headings" aria-hidden="true">
        <span>Member</span>
        <span>Role</span>
        <span>Access</span>
      </div>
      <ul className="settings-members-list">
        {members.map((member) => {
          const self = member.user_id === session.user_id
          const initials = member.email
            .split('@')[0]
            .split(/[.\-_]/)
            .map((part) => part[0])
            .slice(0, 2)
            .join('')
            .toUpperCase()
          return (
            <li className="settings-member-row" key={member.user_id}>
              <div className="member-identity">
                <span className="member-avatar" aria-hidden="true">
                  {initials}
                </span>
                <div>
                  <strong>
                    {member.email}
                    {self && <span className="member-you">You</span>}
                  </strong>
                  <span className={member.revoked_at || member.disabled_at ? 'member-inactive' : ''}>
                    <i aria-hidden="true" />
                    {member.disabled_at
                      ? 'Account disabled'
                      : member.revoked_at
                        ? 'Access revoked'
                        : 'Active'}
                  </span>
                </div>
              </div>
              <span className={`member-role-label${member.role === 'administrator' ? ' is-admin' : ''}`}>
                {member.role === 'administrator' && <ShieldCheck size={13} aria-hidden="true" />}
                {member.role === 'administrator' ? 'Administrator' : 'Member'}
              </span>
              {self ? (
                <span className="member-self-note">Your account</span>
              ) : (
                <MemberDialog
                  member={member}
                  workspaceId={workspaceId}
                  workspaceName={session.memberships.find(item => item.workspace_id === workspaceId)?.workspace_name || 'this workspace'}
                  csrfToken={session.csrf_token}
                  onChanged={(updated) => {
                    onChanged(updated)
                    setNotice(
                      updated.revoked_at
                        ? 'Membership revoked and active sessions ended.'
                        : 'Membership updated.',
                    )
                  }}
                />
              )}
            </li>
          )
        })}
      </ul>
      <p className="members-footer">
        <ShieldCheck size={15} aria-hidden="true" /> Your own role must be changed by another administrator.
        The last active administrator cannot be removed.
      </p>
    </div>
  )
}
