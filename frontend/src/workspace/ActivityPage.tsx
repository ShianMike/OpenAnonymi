import { useEffect, useState } from 'react'
import { RotateCw } from 'lucide-react'
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
import type { DocumentMap } from './activity/activityPresentation'
import './activity/activity.css'

type Data =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; value: ActivityView; documents: DocumentMap }

export function ActivityPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
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
          message:
            activity.reason instanceof Error ? activity.reason.message : 'Activity could not be loaded.',
        })
        return
      }
      setData({
        kind: 'ready',
        value: activity.value,
        documents:
          documents.status === 'fulfilled'
            ? Object.fromEntries(documents.value.map((item) => [item.id, item]))
            : {},
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])
  const reload = () => {
    setData({ kind: 'loading' })
    setAttempt((value) => value + 1)
  }
  return (
    <section className="activity-page" aria-labelledby="activity-title">
      <PageHeader
        title="Activity"
        titleId="activity-title"
        description="Follow the work. A clear history of your reviews and workspace activity."
        action={
          <button className="quiet-button" type="button" disabled={data.kind === 'loading'} onClick={reload}>
            <RotateCw size={15} aria-hidden="true" /> Refresh
          </button>
        }
      />
      {session.memberships.length > 1 && (
        <div className="workspace-picker">
          <label htmlFor="activity-workspace">Workspace</label>
          <GlassSelect
            id="activity-workspace"
            value={workspaceId}
            onValueChange={(value) => {
              setWorkspaceId(value)
              setData({ kind: 'loading' })
            }}
          >
            {session.memberships.map((membership, index) => (
              <option key={membership.workspace_id} value={membership.workspace_id}>
                {membership.workspace_name || `Workspace ${index + 1}`}
              </option>
            ))}
          </GlassSelect>
        </div>
      )}
      {data.kind === 'loading' && (
        <LoadingState label="Loading activity…" description="Bringing your workspace history into view." />
      )}
      {data.kind === 'error' && (
        <InlineNotice error>
          <p>{data.message}</p>
          <button type="button" onClick={reload}>
            Retry activity
          </button>
        </InlineNotice>
      )}
      {data.kind === 'ready' && (
        <div className="activity-layout">
          <ActivityFeed
            key={workspaceId}
            value={data.value}
            documents={data.documents}
            workspaceId={workspaceId}
          />
          <ActivitySummary value={data.value} />
        </div>
      )}
    </section>
  )
}
