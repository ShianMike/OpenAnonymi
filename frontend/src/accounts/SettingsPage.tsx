import { useEffect, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { Clock3, UserRound, Users } from 'lucide-react'
import {
  getMembers,
  getWorkspaceSettings,
  type MemberView,
  type SessionView,
  type WorkspaceSettingsView,
} from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { InlineNotice } from '../ui/WorkspaceControls'
import { AccountPanel } from './settings/AccountPanel'
import { RetentionPanel } from './settings/RetentionPanel'
import { MembersPanel } from './settings/MembersPanel'
import './settings/settings.css'

type Data =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; settings: WorkspaceSettingsView; members: MemberView[] }

export function SettingsPage({
  session,
  onPasswordChanged,
}: {
  session: SessionView
  onPasswordChanged: () => void
}) {
  const adminWorkspaces = session.memberships.filter((item) => item.role === 'administrator')
  const [workspaceId, setWorkspaceId] = useState(adminWorkspaces[0]?.workspace_id ?? '')
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<Data>({ kind: 'loading' })
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.all([
      getWorkspaceSettings(workspaceId, controller.signal),
      getMembers(workspaceId, controller.signal),
    ])
      .then(([settings, members]) => {
        if (!controller.signal.aborted) setData({ kind: 'ready', settings, members })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setData({
            kind: 'error',
            message: cause instanceof Error ? cause.message : 'Settings could not be loaded.',
          })
      })
    return () => controller.abort()
  }, [workspaceId, attempt])
  function reload() {
    setData({ kind: 'loading' })
    setAttempt((value) => value + 1)
  }
  function updateMember(member: MemberView) {
    setData((current) =>
      current.kind !== 'ready' || current.settings.id !== workspaceId
        ? current
        : {
            ...current,
            members: current.members.some((item) => item.user_id === member.user_id)
              ? current.members.map((item) => (item.user_id === member.user_id ? member : item))
              : [...current.members, member],
          },
    )
  }
  const loading = (
    <LoadingState label="Loading workspace settings…" description="Checking the saved defaults and workspace members." shape="form" />
  )
  const failure = data.kind === 'error' && (
    <InlineNotice error>
      <p>{data.message}</p>
      <button type="button" onClick={reload}>
        Retry settings
      </button>
    </InlineNotice>
  )
  return (
    <section className="settings-hub">
      <PageHeader
        title="Settings"
        description="A workspace that works your way. Manage your account, retention, and team."
      />
      <Tabs.Root defaultValue="account" className="settings-tabs">
        <div className="settings-tab-bar">
          <Tabs.List aria-label="Settings sections">
            <Tabs.Trigger value="account">
              <UserRound size={16} aria-hidden="true" /> Account
            </Tabs.Trigger>
            {!!workspaceId && (
              <>
                <Tabs.Trigger value="retention">
                  <Clock3 size={16} aria-hidden="true" /> Retention
                </Tabs.Trigger>
                <Tabs.Trigger value="members">
                  <Users size={16} aria-hidden="true" /> Members
                  {data.kind === 'ready' && <span>{data.members.length}</span>}
                </Tabs.Trigger>
              </>
            )}
          </Tabs.List>
          {adminWorkspaces.length > 1 && (
            <div className="settings-workspace">
              <label className="sr-only" htmlFor="admin-workspace">
                Workspace
              </label>
              <GlassSelect
                id="admin-workspace"
                value={workspaceId}
                onValueChange={(value) => {
                  setData({ kind: 'loading' })
                  setWorkspaceId(value)
                }}
              >
                {adminWorkspaces.map((item) => (
                  <option key={item.workspace_id} value={item.workspace_id}>
                    {item.workspace_name || 'Workspace'}
                  </option>
                ))}
              </GlassSelect>
            </div>
          )}
        </div>
        <Tabs.Content value="account" forceMount>
          <AccountPanel session={session} onPasswordChanged={onPasswordChanged} />
          {!workspaceId && (
            <p className="settings-admin-note">
              Workspace membership and defaults are managed by an administrator.
            </p>
          )}
        </Tabs.Content>
        {!!workspaceId && (
          <>
            <Tabs.Content value="retention" forceMount>
              {data.kind === 'loading'
                ? loading
                : failure ||
                  (data.kind === 'ready' && (
                    <RetentionPanel
                      key={workspaceId}
                      settings={data.settings}
                      csrfToken={session.csrf_token}
                      onSaved={(settings) =>
                        setData((current) =>
                          current.kind === 'ready' && current.settings.id === settings.id
                            ? { ...current, settings }
                            : current,
                        )
                      }
                      onReload={reload}
                    />
                  ))}
            </Tabs.Content>
            <Tabs.Content value="members" forceMount>
              {data.kind === 'loading'
                ? loading
                : failure ||
                  (data.kind === 'ready' && (
                    <MembersPanel
                      key={workspaceId}
                      members={data.members}
                      session={session}
                      workspaceId={workspaceId}
                      onChanged={updateMember}
                    />
                  ))}
            </Tabs.Content>
          </>
        )}
      </Tabs.Root>
    </section>
  )
}
