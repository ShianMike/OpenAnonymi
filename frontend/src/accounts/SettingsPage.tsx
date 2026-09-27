import { useEffect, useState, type FormEvent } from 'react'
import {
  changeMemberRole, getMembers, getWorkspaceSettings, inviteMember,
  restoreMember, revokeMember, updateWorkspaceSettings,
  type MemberView, type SessionView, type WorkspaceSettingsView,
} from '../api/client'

type Data =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; settings: WorkspaceSettingsView; members: MemberView[] }

type Role = 'member' | 'administrator'

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

function MemberRow({
  member, isSelf, busy, onRoleChange, onRevoke, onRestore,
}: {
  member: MemberView
  isSelf: boolean
  busy: boolean
  onRoleChange: (role: Role) => void
  onRevoke: () => void
  onRestore: () => void
}) {
  const [role, setRole] = useState<Role>(member.role)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  const revoked = member.revoked_at !== null
  return (
    <li>
      <strong>{member.email}</strong> — {revoked ? 'revoked' : member.role}
      {member.disabled_at && ' — account disabled'}
      {!isSelf && !revoked && (
        <div>
          <label htmlFor={`role-${member.user_id}`}>Role for {member.email}</label>{' '}
          <select id={`role-${member.user_id}`} value={role}
            onChange={(event) => setRole(event.target.value as Role)} disabled={busy}>
            <option value="member">Member</option>
            <option value="administrator">Administrator</option>
          </select>{' '}
          <button type="button" disabled={busy || role === member.role}
            onClick={() => onRoleChange(role)}>Save role</button>{' '}
          {confirmRevoke ? (
            <>
              <button type="button" disabled={busy} onClick={() => {
                setConfirmRevoke(false)
                onRevoke()
              }}>Confirm revoke</button>{' '}
              <button type="button" disabled={busy}
                onClick={() => setConfirmRevoke(false)}>Cancel</button>
            </>
          ) : (
            <button type="button" disabled={busy}
              onClick={() => setConfirmRevoke(true)}>Revoke access</button>
          )}
        </div>
      )}
      {!isSelf && revoked && !member.disabled_at && (
        <div><button type="button" disabled={busy} onClick={onRestore}>Restore membership</button></div>
      )}
      {isSelf && <p>Your own role must be changed by another administrator.</p>}
    </li>
  )
}

export function SettingsPage({ session }: { session: SessionView }) {
  const adminWorkspaces = session.memberships.filter((item) => item.role === 'administrator')
  const [workspaceId, setWorkspaceId] = useState(adminWorkspaces[0]?.workspace_id ?? '')
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [contentDays, setContentDays] = useState(7)
  const [activityDays, setActivityDays] = useState(90)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<Role>('member')

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.all([
      getWorkspaceSettings(workspaceId, controller.signal),
      getMembers(workspaceId, controller.signal),
    ]).then(([settings, members]) => {
      if (controller.signal.aborted) return
      setContentDays(settings.content_retention_days)
      setActivityDays(settings.activity_retention_days)
      setData({ kind: 'ready', settings, members })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({ kind: 'error', message: messageFrom(cause) })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setNotice(message)
      setAttempt((value) => value + 1)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setBusy(false)
    }
  }

  if (adminWorkspaces.length === 0) {
    return (
      <section>
        <h1>Settings</h1>
        <p>Signed in as {session.email}. Workspace membership and defaults are managed by an administrator.</p>
      </section>
    )
  }

  return (
    <section>
      <h1>Settings</h1>
      {adminWorkspaces.length > 1 && (
        <>
          <label htmlFor="admin-workspace">Workspace</label>{' '}
          <select id="admin-workspace" value={workspaceId}
            onChange={(event) => {
              setData({ kind: 'loading' })
              setWorkspaceId(event.target.value)
            }}>
            {adminWorkspaces.map((item) => (
              <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_id}</option>
            ))}
          </select>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {data.kind === 'loading' && <p role="status">Loading workspace settings…</p>}
      {data.kind === 'error' && (
        <div role="alert">
          <p>{data.message}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <p>Workspace: {data.settings.name}</p>
          <form onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault()
            void run(
              () => updateWorkspaceSettings(
                workspaceId, data.settings.settings_version, contentDays,
                activityDays, session.csrf_token,
              ),
              'Workspace defaults saved. Existing document expiry dates were not changed.',
            )
          }}>
            <h2>Retention defaults</h2>
            <label htmlFor="content-days">Document content days (1–30)</label>{' '}
            <input id="content-days" type="number" min={1} max={30} required
              value={contentDays} onChange={(event) => setContentDays(Number(event.target.value))} />{' '}
            <label htmlFor="activity-days">Activity days (1–365)</label>{' '}
            <input id="activity-days" type="number" min={1} max={365} required
              value={activityDays} onChange={(event) => setActivityDays(Number(event.target.value))} />{' '}
            <button type="submit" disabled={busy}>Save defaults</button>{' '}
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>Reload</button>
          </form>
          <section aria-labelledby="members-title">
            <h2 id="members-title">Members</h2>
            <p>Invitations are emailed when the workspace operator has configured SMTP.</p>
            <form onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              void run(
                () => inviteMember(workspaceId, inviteEmail, inviteRole, session.csrf_token),
                'Invitation sent. The member can set a password using the code in email.',
              )
            }}>
              <label htmlFor="invite-email">New member email</label>{' '}
              <input id="invite-email" type="email" required value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)} />{' '}
              <label htmlFor="invite-role">Role</label>{' '}
              <select id="invite-role" value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as Role)}>
                <option value="member">Member</option>
                <option value="administrator">Administrator</option>
              </select>{' '}
              <button type="submit" disabled={busy}>Send invitation</button>
            </form>
            <ul>
              {data.members.map((member) => (
                <MemberRow key={`${member.user_id}-${member.role}`} member={member}
                  isSelf={member.user_id === session.user_id} busy={busy}
                  onRoleChange={(role) => void run(
                    () => changeMemberRole(
                      workspaceId, member.user_id, role, session.csrf_token,
                    ), 'Role saved.',
                  )}
                  onRevoke={() => void run(
                    () => revokeMember(workspaceId, member.user_id, session.csrf_token),
                    'Membership revoked and active sessions ended.',
                  )}
                  onRestore={() => void run(
                    () => restoreMember(workspaceId, member.user_id, session.csrf_token),
                    'Membership restored. The member must sign in again.',
                  )} />
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  )
}
