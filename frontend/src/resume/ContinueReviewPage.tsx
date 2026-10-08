import { RefreshCw } from 'lucide-react'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { LoadingState } from '../loading/LoadingState'
import { GlassSelect } from '../ui/GlassSelect'
import { useLastReview } from './lastReview'
import { useContinueReviews } from './useContinueReviews'
import { reviewQueue } from './reviewQueue'
import { ReviewQueueList } from './ReviewQueueList'
import { LastReviewCard } from './LastReviewCard'
import { rememberReviewWorkspace, useReviewWorkspace } from './reviewWorkspace'
import './continue-review.css'

export function ContinueReviewPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const preferred = useReviewWorkspace(session.user_id)
  const membership = session.memberships.find((item) => item.workspace_id === params.get('workspace'))
    ?? session.memberships.find((item) => item.workspace_id === preferred) ?? session.memberships[0]
  const workspaceId = membership?.workspace_id ?? ''
  const lastId = useLastReview(session.user_id, workspaceId)
  const { data, retry } = useContinueReviews(session.user_id, workspaceId)
  useEffect(() => {
    if (!workspaceId) return
    rememberReviewWorkspace(session.user_id, workspaceId)
    if (params.get('workspace') !== workspaceId) setParams({ workspace: workspaceId }, { replace: true })
  }, [session.user_id, workspaceId, params, setParams])
  const queue = data.kind === 'ready' ? reviewQueue(data.items, lastId, data.checkedAt) : null
  return <section className="continue-page" aria-labelledby="continue-title">
    <PageHeader title="Continue review" titleId="continue-title"
      description="Finish your work, or check a review shared with you."
      action={<div className="continue-heading-tools">
      {session.memberships.length > 1 ? <div className="continue-workspace-picker">
        <label htmlFor="continue-workspace">Workspace</label>
        <GlassSelect id="continue-workspace" value={workspaceId}
          onValueChange={(value) => setParams({ workspace: value })}>
          {session.memberships.map((item) => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name}</option>)}
        </GlassSelect>
      </div> : <span className="continue-workspace-name">{membership?.workspace_name ?? 'No active workspace'}</span>}
      <button type="button" className="quiet-button" aria-label="Refresh reviews" onClick={retry} disabled={data.kind === 'loading' || (data.kind === 'ready' && data.refreshing)}>
        <RefreshCw size={16} aria-hidden="true" /> {data.kind === 'ready' && data.refreshing ? 'Refreshing…' : 'Refresh'}
      </button>
      </div>} />
    {!membership ? <p role="status">You need an active workspace membership to continue a review.</p> : <>
      {data.kind === 'loading' && <LoadingState label="Checking your available reviews…" description="Finding your unfinished work and assigned reviews." />}
      {data.kind === 'error' && <div className="continue-notice" role="alert">
        <h2>Your reviews couldn’t be checked</h2><p>{data.message}</p>
        <button type="button" onClick={retry}>Retry reviews</button>
      </div>}
      {data.kind === 'ready' && queue && <>
        {data.unavailable && <p className="continue-notice" role="status">Your last review is no longer available. It may have expired or your access changed. Choose another review below.</p>}
        <LastReviewCard item={queue.last} now={data.checkedAt} workspaceId={workspaceId} />
        <div className="continue-queues">
          <ReviewQueueList key={`own.${workspaceId}`} items={queue.unfinished} now={data.checkedAt} workspaceId={workspaceId} />
          <ReviewQueueList key={`assigned.${workspaceId}`} items={queue.assigned} assigned now={data.checkedAt} workspaceId={workspaceId} />
        </div>
      </>}
    </>}
  </section>
}
