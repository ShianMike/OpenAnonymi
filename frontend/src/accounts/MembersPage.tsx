import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiRequestError, getMembers, type MemberView, type SessionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { InlineNotice, RefreshButton } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { MembersPanel } from './settings/MembersPanel'
import { InviteDialog } from './settings/InviteDialog'
import { memberStatus } from './settings/memberPresentation'
import './members.css'

type Data = { kind: 'loading' } | { kind: 'error'; scope: string; message: string }
  | { kind: 'ready'; scope: string; members: MemberView[] }

export function MembersPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const workspaces = session.memberships.filter(item => item.role === 'administrator')
  const requested = params.get('workspace')
  const workspace = requested ? workspaces.find(item => item.workspace_id === requested) : workspaces[0]
  const workspaceId = workspace?.workspace_id ?? ''
  const scope = `${workspaceId}.${session.user_id}.${session.csrf_token}`
  const [stored, setData] = useState<Data>({ kind: 'loading' })
  const data: Data = stored.kind === 'loading' || stored.scope === scope ? stored : { kind: 'loading' }
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState('')
  const view = params.get('view') === 'inactive' ? 'inactive' : 'active'
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getMembers(workspaceId, controller.signal)
      .then(members => { if (!controller.signal.aborted) setData({ kind: 'ready', scope, members }) })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setData({ kind: 'error', scope,
          message: cause instanceof Error ? cause.message : 'Members could not be loaded.' })
      })
    return () => controller.abort()
  }, [workspaceId, scope, attempt])
  const onRequestFailed = useCallback((cause: unknown) => {
    if (cause instanceof ApiRequestError && (cause.status === 401 || cause.code === 'workspace_not_found')) {
      setData({ kind: 'error', scope, message: 'The member list is no longer available with your current access. Refresh to check again.' })
      setNotice('')
    }
  }, [scope])
  function reload() { setData({ kind: 'loading' }); setNotice(''); setAttempt(value => value + 1) }
  function changeView(nextView: 'active' | 'inactive') {
    setParams(current => { const next = new URLSearchParams(current); if (nextView === 'inactive') next.set('view', nextView); else next.delete('view'); return next }, { replace: true })
  }
  function updated(member: MemberView, message: string) {
    setData(current => current.kind !== 'ready' || current.scope !== scope ? current : {
      ...current, members: current.members.some(item => item.user_id === member.user_id)
        ? current.members.map(item => item.user_id === member.user_id ? member : item) : [...current.members, member],
    })
    setNotice(message)
    changeView(memberStatus(member) === 'active' ? 'active' : 'inactive')
  }
  return <section className="members-page" aria-labelledby="members-title">
    <header className="members-header"><div><h1 id="members-title">Members</h1><p>Bring people into your workspace. Keep their access clear.</p></div>
      {workspace && <div className="members-header-actions"><RefreshButton label="Refresh members" pending={data.kind === 'loading'} onClick={reload} />
        {data.kind === 'ready' && <InviteDialog key={scope} workspaceId={workspaceId} workspaceName={workspace.workspace_name} csrfToken={session.csrf_token}
          onInvited={member => updated(member, `Invitation sent to ${member.email}. They can set up their new account using the email code.`)} onAssigned={setNotice} onRequestFailed={onRequestFailed} />}
      </div>}
    </header>
    {workspaces.length > 1 && <div className="members-workspace-picker"><label htmlFor="members-workspace">Workspace</label><GlassSelect id="members-workspace" value={workspaceId} onValueChange={id => {
      setData({ kind: 'loading' }); setNotice(''); setParams({ workspace: id })
    }}>{workspaces.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}</GlassSelect></div>}
    {!workspace ? <InlineNotice>Only workspace administrators can manage members in the selected workspace.</InlineNotice>
      : <>
        {notice && <InlineNotice>{notice}</InlineNotice>}
        {data.kind === 'error' ? <InlineNotice error title="Workspace members are unavailable" actions={<button type="button" className="people-button" onClick={reload}>Retry members</button>}>{data.message}</InlineNotice>
          : data.kind === 'ready' ? <MembersPanel key={scope} members={data.members} session={session} workspaceId={workspaceId} workspaceName={workspace.workspace_name}
            view={view} onViewChange={changeView} onChanged={updated} onRequestFailed={onRequestFailed} />
            : <LoadingState label="Loading members…" description="Checking workspace access and roles." shape="members" onRetry={reload} />}
      </>}
  </section>
}
