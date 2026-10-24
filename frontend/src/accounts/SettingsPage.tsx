import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiRequestError, getSession, getWorkspaceSettings, type SessionView, type WorkspaceSettingsView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { cn } from '../ui/cn'
import { LoadingState } from '../loading/LoadingState'
import { InlineNotice } from '../ui/WorkspaceControls'
import { NotificationPreferencesPanel } from '../notifications/NotificationPreferencesPanel'
import { AccountPanel } from './settings/AccountPanel'
import { DevicesPanel } from './settings/DevicesPanel'
import { RetentionPanel } from './settings/RetentionPanel'
import { SecurityPanel } from './settings/SecurityPanel'
import { WorkspaceSecurityPanel } from './settings/WorkspaceSecurityPanel'
import { settingsHref, settingsSections, workspaceSettingsError } from './settings/settingsNavigation'
import './settings/settings.css'

const PreferencesPage = lazy(() => import('../appearance/PreferencesPage').then(module => ({ default: module.PreferencesPage })))
type Data = { kind: 'loading' } | { kind: 'error'; scope: string; error: ReturnType<typeof workspaceSettingsError> }
  | { kind: 'ready'; scope: string; settings: WorkspaceSettingsView }

export function SettingsPage({ session, onPasswordChanged, onSessionChanged, onSignedOut }: {
  session: SessionView; onPasswordChanged: () => void; onSessionChanged: (session: SessionView) => void; onSignedOut: () => void
}) {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const adminWorkspaces = session.memberships.filter(item => item.role === 'administrator')
  const requestedWorkspace = params.get('workspace')
  const workspace = requestedWorkspace ? adminWorkspaces.find(item => item.workspace_id === requestedWorkspace) : adminWorkspaces[0]
  const workspaceId = workspace?.workspace_id ?? ''
  const scope = `${workspaceId}.${session.user_id}.${session.csrf_token}`
  const requested = params.get('section')
  const section = settingsSections.find(item => item.id === requested) ?? settingsSections[0]
  const workspaceSection = section.group === 'workspace'
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const contentHeading = useRef<HTMLHeadingElement>(null)
  const current = data.kind !== 'loading' && data.scope !== scope ? { kind: 'loading' as const } : data
  useEffect(() => {
    if (workspaceSection && current.kind === 'error') contentHeading.current?.focus({ preventScroll: true })
  }, [workspaceSection, current.kind])
  const onRequestFailed = useCallback((cause: unknown) => {
    if (cause instanceof ApiRequestError && (cause.status === 401 || cause.code === 'workspace_not_found')) {
      setData({ kind: 'error', scope, error: workspaceSettingsError(cause) })
    }
  }, [scope])
  useEffect(() => {
    if (!workspaceSection || !workspaceId) return
    const controller = new AbortController()
    getWorkspaceSettings(workspaceId, controller.signal)
      .then(settings => { if (!controller.signal.aborted) setData({ kind: 'ready', scope, settings }) })
      .catch(cause => { if (!controller.signal.aborted) setData({ kind: 'error', scope, error: workspaceSettingsError(cause) }) })
    return () => controller.abort()
  }, [workspaceSection, workspaceId, scope, attempt])
  function reload() { setData({ kind: 'loading' }); setAttempt(value => value + 1) }
  function saved(settings: WorkspaceSettingsView) {
    setData(previous => previous.kind === 'ready' && previous.scope === scope && settings.id === workspaceId ? { ...previous, settings } : previous)
  }
  if (requested === 'members') return <Navigate replace to={`/members${requestedWorkspace || workspaceId ? `?workspace=${encodeURIComponent(requestedWorkspace || workspaceId)}` : ''}`} />
  const navigation = settingsSections.filter(item => item.group === 'personal' || adminWorkspaces.length > 0)
  return <section className="settings-page" aria-labelledby="settings-title">
    <header className="settings-page-header"><h1 id="settings-title">Settings</h1><p>Your account, your preferences, and the way your workspace runs.</p></header>
    <div className="settings-layout">
      <nav className="settings-navigation" aria-label="Settings sections">
        <div className="settings-navigation-group"><span>Personal</span>{navigation.filter(item => item.group === 'personal').map(item => <Link key={item.id} to={settingsHref(item.id, requestedWorkspace)} aria-current={section.id === item.id ? 'page' : undefined} className={cn('settings-navigation-link', section.id === item.id && 'is-current')}>{item.label}</Link>)}</div>
        {adminWorkspaces.length > 0 && <div className="settings-navigation-group"><span>Workspace</span>{navigation.filter(item => item.group === 'workspace').map(item => <Link key={item.id} to={settingsHref(item.id, requestedWorkspace || workspaceId)} aria-current={section.id === item.id ? 'page' : undefined} className={cn('settings-navigation-link', section.id === item.id && 'is-current')}>{item.label}</Link>)}</div>}
      </nav>
      <div className="settings-mobile-navigation"><label htmlFor="settings-section">Settings section</label><GlassSelect id="settings-section" value={section.id} onValueChange={id => navigate(settingsHref(id, requestedWorkspace || (settingsSections.find(item => item.id === id)?.group === 'workspace' ? workspaceId : null)))}>{navigation.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</GlassSelect></div>
      <div className="settings-content" key={`${section.id}.${scope}`}>
        <header className="settings-content-header"><h2 ref={contentHeading} tabIndex={-1}>{section.title}</h2><p>{section.description}</p></header>
        {workspaceSection && <div className="settings-workspace-scope"><div><label htmlFor="settings-workspace">Workspace</label>{adminWorkspaces.length > 1 ? <GlassSelect id="settings-workspace" value={workspaceId} onValueChange={id => navigate(settingsHref(section.id, id))}>{adminWorkspaces.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}</GlassSelect> : <strong>{workspace?.workspace_name || 'No administrator access'}</strong>}</div><p>Changes affect members of this workspace.</p></div>}
        {section.id === 'account' && <AccountPanel session={session} onSessionChanged={onSessionChanged} />}
        {section.id === 'security' && <SecurityPanel session={session} onPasswordChanged={onPasswordChanged} onSessionChanged={onSessionChanged} />}
        {section.id === 'devices' && <DevicesPanel csrfToken={session.csrf_token} onSignedOut={onSignedOut} />}
        {section.id === 'notifications' && <><NotificationPreferencesPanel session={session} /><Link className="settings-text-link" to="/notifications">Open your notification inbox</Link></>}
        {section.id === 'appearance' && <Suspense fallback={<LoadingState label="Opening appearance preferences…" shape="form" />}><PreferencesPage /></Suspense>}
        {workspaceSection && (!workspace ? <InlineNotice error title="Administrator access needed" actions={<Link className="settings-button" to={settingsHref('account', null)}>Back to account</Link>}>Only workspace administrators can manage settings for the selected workspace. You can still manage your personal settings.</InlineNotice>
          : current.kind === 'error' ? <InlineNotice error title={current.error.title} actions={<><button type="button" className="settings-button" onClick={reload}>{current.error.retryLabel}</button><Link className="settings-button" to={settingsHref('account', null)}>Back to account</Link></>}>{current.error.message}</InlineNotice>
            : current.kind === 'loading' ? <LoadingState label="Loading workspace settings…" shape="form" onRetry={reload} />
              : section.id === 'retention' ? <RetentionPanel settings={current.settings} csrfToken={session.csrf_token} onSaved={saved} onReload={reload} onRequestFailed={onRequestFailed} />
                : <WorkspaceSecurityPanel settings={current.settings} session={session} onReload={reload} onRequestFailed={onRequestFailed} onSaved={value => { saved(value); void getSession().then(onSessionChanged).catch(() => {}) }} />)}
      </div>
    </div>
  </section>
}
