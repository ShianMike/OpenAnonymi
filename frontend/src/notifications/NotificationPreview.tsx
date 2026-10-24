import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useEffectEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CircleAlert, ShieldCheck } from 'lucide-react'
import { LoadingState } from '../loading/LoadingState'
import { DialogFrame } from '../ui/WorkspaceControls'
import { getNotification, type Notification, type NotificationDetail } from './api'
import { currentReview, notificationDestination, notificationEvents } from './notificationPresentation'

type Preview = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; detail: NotificationDetail }

export function NotificationPreview({ id, read, pending, onViewed, onNavigate, onCloseAutoFocus }: {
  id: string; read: boolean; pending: boolean; onViewed: (notification: Notification) => void
  onNavigate: () => void; onCloseAutoFocus: (event: Event) => void
}) {
  const [data, setData] = useState<Preview>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const viewed = useEffectEvent(onViewed)
  useEffect(() => {
    let controller: AbortController | undefined
    function load() {
      controller?.abort()
      setData({ kind: 'loading' })
      if (document.visibilityState !== 'visible') return
      const current = new AbortController()
      controller = current
      getNotification(id, current.signal).then(detail => {
        if (current.signal.aborted) return
        setData({ kind: 'ready', detail })
        viewed(detail.notification)
      }).catch(cause => {
        if (!current.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'This update could not be loaded.' })
      })
    }
    load()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') load() }, 60_000)
    window.addEventListener('focus', load)
    document.addEventListener('visibilitychange', load)
    return () => { controller?.abort(); window.clearInterval(timer); window.removeEventListener('focus', load); document.removeEventListener('visibilitychange', load) }
  }, [id, attempt])
  return <DialogFrame title="Review update" description="Check what happened before opening the review." className="notification-preview-dialog" onCloseAutoFocus={onCloseAutoFocus}>
    {data.kind === 'loading' && <LoadingState label="Checking this update…" description="Confirming your access and the current review status." shape="form" onRetry={() => setAttempt(value => value + 1)} />}
    {data.kind === 'error' && <div className="notification-preview-error" role="alert"><CircleAlert size={22} aria-hidden="true" /><h3>Update couldn’t be loaded</h3><p>{data.message}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button></div>}
    {data.kind === 'ready' && <NotificationDetailContent detail={data.detail} read={read || !!data.detail.notification.read_at} pending={pending} onNavigate={onNavigate} />}
  </DialogFrame>
}

export function NotificationDetailContent({ detail, read, pending, onNavigate }: {
  detail: NotificationDetail; read: boolean; pending: boolean; onNavigate: () => void
}) {
  const { notification, current } = detail
  const event = notificationEvents[notification.event_code]
  const status = currentReview(detail)
  const destination = notificationDestination(detail)
  return <>
    <div className="notification-preview-event">
      <div className="notification-preview-event-meta"><span>{event.title}</span><span>{pending ? 'Saving read status…' : read ? 'Read' : 'Unread'}</span></div>
      <h3>{notification.document_available ? notification.title || 'Untitled review' : 'Review unavailable'}</h3>
      <p>{event.message}</p>
      <time dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString(undefined, { dateStyle: 'long', timeStyle: 'short' })}</time>
    </div>
    <section className="notification-preview-current" aria-label="Current review status">
      <div className="notification-preview-section-label"><ShieldCheck size={15} aria-hidden="true" />Current review</div>
      <h4>{status.title}</h4><p>{status.message}</p>
      {current && <dl><div><dt>Your access</dt><dd>{current.is_owner ? 'Document owner' : 'Assigned reviewer'}</dd></div>
        {current.approved_at && <div><dt>Approved</dt><dd><time dateTime={current.approved_at}>{new Date(current.approved_at).toLocaleString()}</time></dd></div>}</dl>}
    </section>
    {destination && <p className="notification-preview-note">{notification.event_code === 'comment_added'
      ? 'The discussion shows comments on the current source. Earlier comments may no longer be available.'
      : 'This update records a past event. You’ll open the latest saved version.'}</p>}
    <footer className="notification-preview-actions"><Dialog.Close className="notification-preview-back">Back to inbox</Dialog.Close>
      {destination && <Link className="notification-preview-open" to={destination.to} aria-disabled={pending || undefined}
        tabIndex={pending ? -1 : undefined} onClick={event => { if (pending) event.preventDefault(); else onNavigate() }}>{destination.label}<ArrowRight size={15} aria-hidden="true" /></Link>}
    </footer>
  </>
}
