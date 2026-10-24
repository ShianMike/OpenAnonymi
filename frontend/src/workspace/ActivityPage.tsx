import { useCallback, useEffect, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { useSearchParams } from 'react-router-dom'
import { GlassSelect } from '../ui/GlassSelect'
import {
  getWorkspaceActivity,
  getWorkspaceDocuments,
  type ActivityView,
  type SessionView,
} from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { InlineNotice, RefreshButton } from '../ui/WorkspaceControls'
import { ActivityFeed } from './activity/ActivityFeed'
import { AdminActivityPanel } from './activity/AdminActivityPanel'
import type { DocumentMap } from './activity/activityPresentation'
import './activity/activity.css'

type Data =
  | { kind: 'loading' }
  | { kind: 'error'; scope: string; message: string }
  | { kind: 'ready'; scope: string; value: ActivityView; documents: DocumentMap; titlesUnavailable: boolean; refreshing?: boolean }

export function ActivityPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const workspaceId = session.memberships.find(item => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? ''
  const scope = `${workspaceId}.${session.user_id}.${session.csrf_token}`
  const [stored, setData] = useState<Data>({ kind: 'loading' })
  const data: Data = stored.kind === 'loading' || stored.scope === scope ? stored : { kind: 'loading' }
  const [attempt, setAttempt] = useState(0)
  const [view, setView] = useState('own')
  const administrator = session.memberships.some(member => member.workspace_id === workspaceId && member.role === 'administrator')
  const handleAccessLost = useCallback(() => {
    setView('own')
    setData({ kind: 'error', scope, message: 'Workspace log access could not be verified. Refresh Activity to check your current access.' })
  }, [scope])
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.allSettled([
      getWorkspaceActivity(workspaceId, controller.signal),
      getWorkspaceDocuments(workspaceId, controller.signal),
    ]).then(([activity, documents]) => {
      if (controller.signal.aborted) return
      if (activity.status === 'rejected') {
        setData({
          kind: 'error',
          scope,
          message: activity.reason instanceof Error ? activity.reason.message : 'Activity could not be loaded.',
        })
        return
      }
      setData({
        kind: 'ready',
        scope,
        value: activity.value,
        documents: documents.status === 'fulfilled' ? Object.fromEntries(documents.value.map(item => [item.id, item])) : {},
        titlesUnavailable: documents.status === 'rejected',
      })
    })
    return () => controller.abort()
  }, [workspaceId, scope, attempt])
  const reload = () => {
    setData(current => current.kind === 'ready' ? { ...current, refreshing: true } : { kind: 'loading' })
    setAttempt(value => value + 1)
  }
  return <section className="activity-page" aria-labelledby="activity-title">
    <header className="activity-page-heading"><div><h1 id="activity-title">Activity</h1><p>Follow your reviews, decisions and workspace changes.</p></div>
      <div className="activity-heading-tools">
        {session.memberships.length > 1 ? <div className="activity-workspace-picker">
          <label htmlFor="activity-workspace">Workspace</label>
          <GlassSelect id="activity-workspace" value={workspaceId} onValueChange={value => {
            setData({ kind: 'loading' }); setView('own')
            setParams(current => { const next = new URLSearchParams(current); next.set('workspace', value); return next })
          }}>{session.memberships.map((membership, index) => <option key={membership.workspace_id} value={membership.workspace_id}>
            {membership.workspace_name || `Workspace ${index + 1}`}
          </option>)}</GlassSelect>
        </div> : null}
        <RefreshButton label="Refresh activity" pending={data.kind === 'ready' && !!data.refreshing} disabled={data.kind === 'loading' || !workspaceId} onClick={reload} />
      </div></header>
    {!workspaceId ? <p role="status">You need an active workspace membership to view activity.</p> : <>
      {data.kind === 'loading' && <LoadingState label="Loading activity…" description="Bringing your workspace history into view." shape="timeline" onRetry={reload} />}
      {data.kind === 'error' && <InlineNotice error>
        <p>{data.message}</p><button type="button" onClick={reload}>Retry activity</button>
      </InlineNotice>}
      {data.kind === 'ready' && <>
        <Tabs.Root value={administrator && data.value.workspace_counts !== null ? view : 'own'} onValueChange={setView} className="activity-views">
          <Tabs.List className="activity-view-tabs" aria-label="Activity views">
            <Tabs.Trigger value="own">Your activity</Tabs.Trigger>
            {administrator && data.value.workspace_counts !== null && <Tabs.Trigger value="workspace">Workspace log</Tabs.Trigger>}
          </Tabs.List>
          <Tabs.Content value="own" className="activity-view-content">
            {data.titlesUnavailable && <InlineNotice error>Review titles couldn’t be loaded. Events are still available. Refresh to try again.</InlineNotice>}
            <ActivityFeed key={scope} value={data.value} documents={data.documents} workspaceId={workspaceId} />
          </Tabs.Content>
          {administrator && data.value.workspace_counts !== null && <Tabs.Content value="workspace" className="activity-view-content">
            {data.titlesUnavailable && <InlineNotice error>Review titles couldn’t be loaded. Event records are still available.</InlineNotice>}
            <AdminActivityPanel key={scope} workspaceId={workspaceId} csrf={session.csrf_token} refreshKey={attempt} onAccessLost={handleAccessLost} documents={data.documents} currentUserId={session.user_id} />
          </Tabs.Content>}
        </Tabs.Root>
      </>}
    </>}
  </section>
}
