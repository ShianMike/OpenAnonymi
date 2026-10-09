import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getMembers, type MemberView, type SessionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { PageHeader } from '../ui/PageHeader'
import { InlineNotice, RefreshButton } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { MembersPanel } from './settings/MembersPanel'
import './settings/settings.css'

type Data = { kind: 'loading' } | { kind: 'error'; workspaceId: string; message: string }
  | { kind: 'ready'; workspaceId: string; members: MemberView[] }

export function MembersPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const workspaces = session.memberships.filter(item => item.role === 'administrator')
  const workspace = workspaces.find(item => item.workspace_id === params.get('workspace')) ?? workspaces[0]
  const workspaceId = workspace?.workspace_id ?? ''
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getMembers(workspaceId, controller.signal)
      .then(members => { if (!controller.signal.aborted) setData({ kind: 'ready', workspaceId, members }) })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setData({ kind: 'error', workspaceId,
          message: cause instanceof Error ? cause.message : 'Members could not be loaded.' })
      })
    return () => controller.abort()
  }, [workspaceId, attempt, session.csrf_token])
  function reload() { setData({ kind: 'loading' }); setAttempt(value => value + 1) }
  const ready = data.kind === 'ready' && data.workspaceId === workspaceId

  return <section className="settings-hub members-page" aria-labelledby="members-title">
    <PageHeader title="Members" titleId="members-title" description="Manage who can access each workspace."
      action={workspace && <div className="settings-heading-tools">
        <div className="settings-workspace"><label htmlFor="members-workspace">Workspace</label>
          {workspaces.length > 1 ? <GlassSelect id="members-workspace" value={workspaceId} onValueChange={id => {
            setData({ kind: 'loading' }); setParams({ workspace: id })
          }}>{workspaces.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}</GlassSelect>
            : <span>{workspace.workspace_name}</span>}
        </div>
        <RefreshButton label="Refresh members" pending={data.kind === 'loading'} onClick={reload} />
      </div>} />
    {!workspace ? <InlineNotice>Only workspace administrators can manage members.</InlineNotice>
      : data.kind === 'error' && data.workspaceId === workspaceId ? <InlineNotice error>{data.message}<button type="button" onClick={reload}>Retry members</button></InlineNotice>
      : ready ? <MembersPanel key={workspaceId} members={data.members} session={session} workspaceId={workspaceId} onChanged={member => {
        setData(current => current.kind !== 'ready' || current.workspaceId !== workspaceId ? current : {
          ...current, members: current.members.some(item => item.user_id === member.user_id)
            ? current.members.map(item => item.user_id === member.user_id ? member : item) : [...current.members, member],
        })
      }} /> : <LoadingState label="Loading members…" description="Checking workspace access and roles." />}
  </section>
}
