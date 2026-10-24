import type { ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowUpRight, Check, CircleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DialogFrame } from '../../ui/WorkspaceControls'
import { categoryPresentation } from '../../rules/categoryPresentation'
import type { StyleChoice } from '../../api/client'
import { styleLabel, type ReviewAction } from '../../review/useStyleControls'
import { eventName } from '../events'
import { eventContext, type ActivityEvent, type DocumentMap } from './activityPresentation'

const decisionLabel = (action: ReviewAction | null, style: StyleChoice['style'], style_option: StyleChoice['style_option']) => action
  ? `${{ keep: 'Keep', label: 'Replace', redact: 'Hide' }[action]} · ${styleLabel({ style, style_option }, action)}` : 'Undecided'

export function ActivityEventDetails({ event, documents, workspaceId, currentUserId }: {
  event: ActivityEvent; documents: DocumentMap; workspaceId: string; currentUserId?: string
}) {
  const document = event.document_id ? documents[event.document_id] : undefined
  const admin = 'id' in event ? event : null
  const failed = event.outcome === 'failed'
  return <>
    <div className="activity-detail-body">
      <span className={`activity-detail-outcome${failed ? ' is-failed' : ''}`}>{failed ? <CircleAlert size={15} aria-hidden="true" /> : <Check size={15} aria-hidden="true" />}{failed ? 'Failed' : 'Completed'}</span>
      <dl className="activity-detail-facts">
        <div><dt>When</dt><dd><time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString(undefined, { dateStyle: 'long', timeStyle: 'long' })}</time></dd></div>
        <div><dt>{event.document_id ? 'Review' : 'Area'}</dt><dd>{eventContext(event, documents)}</dd></div>
        {admin && <div><dt>Performed by</dt><dd>{admin.actor_id ? admin.actor_id === currentUserId ? 'You' : `Member ${admin.actor_id.slice(0, 8)}` : 'System or removed member'}</dd></div>}
      </dl>
      {event.document_id && !document && <p className="activity-detail-note">A review link isn’t available for this event. The retained log does not include the review’s source text.</p>}
      {admin && <section className="activity-decision-changes" aria-label="Recorded decision changes">
        <h3>Decision changes{admin.decision_change_count > 0 && <span>{admin.decision_change_count}</span>}</h3>
        {admin.decision_changes.length > 0 ? <>
          <p>Recorded choices, with the source values left out.</p>
          <ul>{admin.decision_changes.map(change => <li key={change.finding_id}>
            <strong>{categoryPresentation[change.category].label}</strong>
            <div><span>Before</span><p>{decisionLabel(change.before_action, change.before_style, change.before_option)}</p></div>
            <div><span>After</span><p>{decisionLabel(change.after_action, change.after_style, change.after_option)}</p></div>
            <small>Finding {change.finding_id}</small>
          </li>)}</ul>
          {admin.decision_change_count > admin.decision_changes.length && <p>Showing the first {admin.decision_changes.length} of {admin.decision_change_count} recorded changes.</p>}
        </> : <p>No decision changes were recorded for this event.</p>}
      </section>}
      <details className="activity-record-details"><summary>Record details</summary><dl className="activity-detail-facts">
        <div><dt>Event type</dt><dd><code>{event.event_code}</code></dd></div>
        {admin && <div><dt>Event ID</dt><dd><code>{admin.id}</code></dd></div>}
        {admin?.actor_id && <div><dt>Member ID</dt><dd><code>{admin.actor_id}</code></dd></div>}
        {event.document_id && <div><dt>Review ID</dt><dd><code>{event.document_id}</code></dd></div>}
        {admin?.decision_version != null && <div><dt>Decision version</dt><dd>{admin.decision_version}</dd></div>}
      </dl></details>
      <p className="activity-detail-note">The activity log records actions, not document content. Matched text, replacement values, comments and Keep reasons are excluded.</p>
    </div>
    <footer className="activity-detail-footer"><Dialog.Close className="activity-button">Close</Dialog.Close>
      {document && <Dialog.Close asChild><Link className="activity-button activity-button-primary" to={`/workspaces/${workspaceId}/documents/${document.id}/history`}>View review history<ArrowUpRight size={14} aria-hidden="true" /></Link></Dialog.Close>}
    </footer>
  </>
}

export function ActivityEventDialog({ trigger, ...props }: {
  trigger: ReactNode; event: ActivityEvent; documents: DocumentMap; workspaceId: string; currentUserId?: string
}) {
  return <Dialog.Root><Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <DialogFrame className="workspace-side-dialog activity-event-dialog" title={eventName(props.event.event_code)} description="Event details from your workspace activity log.">
      <ActivityEventDetails {...props} />
    </DialogFrame>
  </Dialog.Root>
}
