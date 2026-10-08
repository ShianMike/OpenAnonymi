import { useEffect, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { Navigate, useSearchParams } from 'react-router-dom'
import { Clock3, ShieldCheck, UserRound } from 'lucide-react'
import { getSession, getWorkspaceSettings, type SessionView, type WorkspaceSettingsView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { InlineNotice } from '../ui/WorkspaceControls'
import { AccountPanel } from './settings/AccountPanel'
import { RetentionPanel } from './settings/RetentionPanel'
import { SecurityPanel } from './settings/SecurityPanel'
import { WorkspaceSecurityPanel } from './settings/WorkspaceSecurityPanel'
import './settings/settings.css'

type Data = { kind: 'loading' } | { kind: 'error'; workspaceId: string; message: string }
  | { kind: 'ready'; settings: WorkspaceSettingsView }

export function SettingsPage({ session, onPasswordChanged, onSessionChanged, onSignedOut }: {
  session: SessionView
  onPasswordChanged: () => void
  onSessionChanged: (session: SessionView) => void
  onSignedOut: () => void
}) {
  const [params, setParams] = useSearchParams()
  const adminWorkspaces = session.memberships.filter(item => item.role === 'administrator')
  const workspace = adminWorkspaces.find(item => item.workspace_id === params.get('workspace')) ?? adminWorkspaces[0]
  const workspaceId = workspace?.workspace_id ?? ''
  const requested = params.get('section') ?? 'account'
  const section = requested === 'security' || (requested === 'retention' && workspaceId) ? requested : 'account'
  const workspaceSection = requested !== 'members' && !!workspaceId && section !== 'account'
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const settings = data.kind === 'ready' && data.settings.id === workspaceId ? data.settings : null

  useEffect(() => {
    if (!workspaceSection) return
    const controller = new AbortController()
    getWorkspaceSettings(workspaceId, controller.signal)
      .then(value => { if (!controller.signal.aborted) setData({ kind: 'ready', settings: value }) })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setData({ kind: 'error', workspaceId,
          message: cause instanceof Error ? cause.message : 'Workspace settings could not be loaded.' })
      })
    return () => controller.abort()
  }, [workspaceId, workspaceSection, attempt, session.csrf_token])

  function reload() { setData({ kind: 'loading' }); setAttempt(value => value + 1) }
  function saved(value: WorkspaceSettingsView) {
    setData(current => current.kind === 'ready' && current.settings.id === value.id ? { ...current, settings: value } : current)
  }
  const workspaceState = data.kind === 'error' && data.workspaceId === workspaceId
    ? <InlineNotice error>{data.message}<button type="button" onClick={reload}>Retry workspace settings</button></InlineNotice>
    : <LoadingState label="Loading workspace settings…" description="Checking the saved workspace defaults." shape="form" />

  if (requested === 'members') return <Navigate replace to={`/members${workspaceId ? `?workspace=${encodeURIComponent(workspaceId)}` : ''}`} />

  return <section className="settings-hub" aria-labelledby="settings-title">
    <PageHeader title="Settings" titleId="settings-title" description="Your account, sign-in security, and workspace retention."
      action={workspaceSection ? <div className="settings-workspace">
        <label htmlFor="admin-workspace">Workspace</label>
        {adminWorkspaces.length > 1 ? <GlassSelect id="admin-workspace" value={workspaceId} onValueChange={id => {
          setData({ kind: 'loading' })
          setParams(current => { const next = new URLSearchParams(current); next.set('workspace', id); return next })
        }}>{adminWorkspaces.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}</GlassSelect>
          : <span>{workspace.workspace_name}</span>}
      </div> : undefined} />
    <Tabs.Root value={section} onValueChange={value => setParams(current => {
      const next = new URLSearchParams(current); next.set('section', value); return next
    })} className="settings-tabs">
      <div className="settings-tab-bar">
        <Tabs.List aria-label="Settings sections">
          <Tabs.Trigger value="account"><UserRound size={16} aria-hidden="true" />Account</Tabs.Trigger>
          <Tabs.Trigger value="security"><ShieldCheck size={16} aria-hidden="true" />Security</Tabs.Trigger>
          {!!workspaceId && <Tabs.Trigger value="retention"><Clock3 size={16} aria-hidden="true" />Retention</Tabs.Trigger>}
        </Tabs.List>
      </div>
      <Tabs.Content value="account" forceMount>
        <AccountPanel session={session} />
      </Tabs.Content>
      <Tabs.Content value="security">
        <SecurityPanel session={session} onPasswordChanged={onPasswordChanged} onSignedOut={onSignedOut} onSessionChanged={updated => { onSessionChanged(updated); reload() }} />
        {!!workspaceId && (settings ? <WorkspaceSecurityPanel key={workspaceId} settings={settings} session={session}
          onSaved={value => {
            saved(value)
            void getSession().then(onSessionChanged).catch(() => { /* Retry through the next account action. */ })
          }} onReload={reload} /> : workspaceState)}
      </Tabs.Content>
      {!!workspaceId && <Tabs.Content value="retention" forceMount>
        {settings ? <RetentionPanel key={workspaceId} settings={settings} csrfToken={session.csrf_token} onSaved={saved} onReload={reload} /> : workspaceState}
      </Tabs.Content>}
    </Tabs.Root>
  </section>
}
