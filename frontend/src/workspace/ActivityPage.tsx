import { useCallback, useEffect, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { History, RotateCw, Users } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import {
  getWorkspaceActivity,
  getWorkspaceDocuments,
  type ActivityView,
  type SessionView,
} from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { InlineNotice } from '../ui/WorkspaceControls'
import { ActivityFeed } from './activity/ActivityFeed'
import { ActivitySummary } from './activity/ActivitySummary'
import { AdminActivityPanel } from './activity/AdminActivityPanel'
import type { DocumentMap } from './activity/activityPresentation'
import './activity/activity.css'

type Data =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; value: ActivityView; documents: DocumentMap; titlesUnavailable: boolean; refreshing?: boolean }

export function ActivityPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [view, setView] = useState('own')
  const administrator = session.memberships.some(member => member.workspace_id === workspaceId && member.role === 'administrator')
  const clearAdministratorCounts = useCallback(() => {
    setData(current => current.kind === 'ready' ? { ...current, value: { ...current.value, workspace_counts: null } } : current)
  }, [])
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
          message: activity.reason instanceof Error ? activity.reason.message : 'Activity could not be loaded.',
        })
        return
      }
      setData({
        kind: 'ready',
        value: activity.value,
        documents: documents.status === 'fulfilled' ? Object.fromEntries(documents.value.map(item => [item.id, item])) : {},
        titlesUnavailable: documents.status === 'rejected',
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt, session.csrf_token])
  const reload = () => {
    setData(current => current.kind === 'ready' ? { ...current, refreshing: true } : { kind: 'loading' })
    setAttempt(value => value + 1)
  }
  return <section className="activity-page" aria-labelledby="activity-title">
    <PageHeader title="Activity" titleId="activity-title"
      description="Find a recent action, or look back through your workspace."
      action={<div className="activity-heading-tools">
        {session.memberships.length > 1 ? <div className="activity-workspace-picker">
          <label htmlFor="activity-workspace">Workspace</label>
          <GlassSelect id="activity-workspace" value={workspaceId} onValueChange={value => {
            setWorkspaceId(value); setData({ kind: 'loading' }); setView('own')
          }}>{session.memberships.map((membership, index) => <option key={membership.workspace_id} value={membership.workspace_id}>
            {membership.workspace_name || `Workspace ${index + 1}`}
          </option>)}</GlassSelect>
        </div> : <span className="activity-workspace-name">{session.memberships[0]?.workspace_name ?? 'No active workspace'}</span>}
        <button className="quiet-button" type="button" aria-label="Refresh activity" disabled={data.kind === 'loading' || (data.kind === 'ready' && data.refreshing) || !workspaceId} onClick={reload}>
          <RotateCw size={16} aria-hidden="true" /> {data.kind === 'ready' && data.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>} />
    {!workspaceId ? <p role="status">You need an active workspace membership to view activity.</p> : <>
      {data.kind === 'loading' && <LoadingState label="Loading activity…" description="Bringing your workspace history into view." />}
      {data.kind === 'error' && <InlineNotice error>
        <p>{data.message}</p><button type="button" onClick={reload}>Retry activity</button>
      </InlineNotice>}
      {data.kind === 'ready' && <>
        <ActivitySummary value={data.value} />
        <Tabs.Root value={administrator ? view : 'own'} onValueChange={setView} className="activity-views">
          <Tabs.List className="activity-view-tabs" aria-label="Activity views">
            <Tabs.Trigger value="own"><History size={16} aria-hidden="true" />Your activity</Tabs.Trigger>
            {administrator && <Tabs.Trigger value="workspace"><Users size={16} aria-hidden="true" />Workspace activity</Tabs.Trigger>}
          </Tabs.List>
          <Tabs.Content value="own" className="activity-view-content">
            {data.titlesUnavailable && <InlineNotice error>Review titles couldn’t be loaded. Events are still available. Refresh to try again.</InlineNotice>}
            <ActivityFeed key={workspaceId} value={data.value} documents={data.documents} workspaceId={workspaceId} />
          </Tabs.Content>
          {administrator && <Tabs.Content value="workspace" className="activity-view-content">
            <AdminActivityPanel key={`${workspaceId}.${session.csrf_token}`} workspaceId={workspaceId} csrf={session.csrf_token} refreshKey={attempt} onAccessLost={clearAdministratorCounts} />
          </Tabs.Content>}
        </Tabs.Root>
      </>}
    </>}
  </section>
}
