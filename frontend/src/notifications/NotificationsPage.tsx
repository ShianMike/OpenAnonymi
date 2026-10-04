import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Check, Circle } from 'lucide-react'
import type { SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { PageHeader } from '../ui/PageHeader'
import { InlineNotice } from '../ui/WorkspaceControls'
import { getNotifications, markAllNotificationsRead, markNotificationRead, notificationChanged, type Notification, type NotificationPage } from './api'
import './notifications.css'

const messages: Record<Notification['event_code'], string> = {
  review_assigned: 'A review was assigned to you',
  review_unassigned: 'Your reviewer assignment was removed',
  approval_requested: 'Your approval was requested',
  review_approved: 'Your review was approved',
  approval_invalidated: 'A review changed and needs fresh approval',
  comment_added: 'A comment was added to a review',
}

export function NotificationsPage({ session }: { session: SessionView }) {
  const [page, setPage] = useState<NotificationPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  const mounted = useRef(false)
  const generation = useRef(0)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; generation.current += 1 }
  }, [])
  useEffect(() => {
    let controller: AbortController | undefined
    function refresh() {
      controller?.abort()
      generation.current += 1
      // Remove previously decrypted titles before an access recheck, including
      // when a tab is hidden. A failed recheck never retains old title data.
      setPage(null)
      setError(null)
      if (document.visibilityState !== 'visible') return
      controller = new AbortController()
      const current = controller
      getNotifications(current.signal).then((result) => {
        if (!current.signal.aborted) setPage(result)
      }).catch((cause: unknown) => {
        if (!current.signal.aborted) setError(cause instanceof Error ? cause.message : 'Notifications could not be loaded.')
      })
    }
    refresh()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') refresh() }, 60_000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      controller?.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [session.user_id, attempt])
  async function read(id?: string) {
    if (pending) return
    setPending(id ?? 'all'); setError(null); setNotice(null)
    try {
      if (id) await markNotificationRead(id, session.csrf_token)
      else await markAllNotificationsRead(session.csrf_token)
      if (!mounted.current) return
      setPage((current) => current && { ...current, items: current.items.map((item) =>
        !item.read_at && (!id || item.id === id) ? { ...item, read_at: new Date().toISOString() } : item) })
      setNotice(id ? 'Notification marked as read.' : 'All notifications marked as read.')
      notificationChanged()
    } catch (cause: unknown) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'Read status could not be saved.')
    } finally { if (mounted.current) setPending(null) }
  }
  async function more() {
    if (!page?.next_cursor || pending) return
    const expected = generation.current
    setPending('more'); setError(null)
    try {
      const next = await getNotifications(undefined, page.next_cursor)
      if (!mounted.current || generation.current !== expected) return
      setPage((current) => current && { next_cursor: next.next_cursor, items: [...current.items, ...next.items.filter((row) => !current.items.some((item) => item.id === row.id))] })
    } catch (cause: unknown) {
      if (mounted.current && generation.current === expected) setError(cause instanceof Error ? cause.message : 'More notifications could not be loaded.')
    } finally { if (mounted.current) setPending(null) }
  }
  return <section className="notifications-page" aria-labelledby="notifications-title">
    <PageHeader title="Notifications" titleId="notifications-title" description="Review assignments, approvals, and discussion across your workspaces."
      action={<button type="button" className="button-secondary" disabled={!!pending || !page?.items.some((item) => !item.read_at)} onClick={() => void read()}>{pending === 'all' ? 'Saving…' : 'Mark all as read'}</button>} />
    {notice && <InlineNotice>{notice}</InlineNotice>}
    {error && <InlineNotice error>{error} <button type="button" onClick={() => setAttempt((value) => value + 1)}>Refresh notifications</button></InlineNotice>}
    {!page && !error && <LoadingState label="Checking notifications…" shape="cards" />}
    {page && <div className="workspace-panel notification-inbox">
      {!page.items.length ? <div className="notification-empty"><Bell size={24} aria-hidden="true" /><h2>You’re all caught up</h2><p>Your review notifications will appear here.</p></div>
        : <ul className="notification-list">{page.items.map((item) => <li key={item.id} className={item.read_at ? 'notification is-read' : 'notification'}>
          <span className="notification-status" title={item.read_at ? 'Read' : 'Unread'}>{item.read_at ? <Check size={16} aria-label="Read" /> : <Circle size={12} aria-label="Unread" />}</span>
          <div className="notification-details"><h2>{messages[item.event_code]}</h2>
            {item.document_available && item.document_id ? <Link to={`/documents/${encodeURIComponent(item.document_id)}/edit`}>{item.title || 'Untitled document'}</Link>
              : <p className="field-note">Document unavailable. Its access may have changed, or it may have expired or been deleted.</p>}
            <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
          </div>
          {!item.read_at && <button type="button" className="button-secondary" disabled={!!pending} onClick={() => void read(item.id)} aria-label={`Mark as read: ${messages[item.event_code]}`}>{pending === item.id ? 'Saving…' : 'Mark as read'}</button>}
        </li>)}</ul>}
      {page.next_cursor && <button type="button" className="button-secondary notification-more" disabled={!!pending} onClick={() => void more()}>{pending === 'more' ? 'Loading…' : 'Load more notifications'}</button>}
    </div>}
    <p className="field-note">Notifications are kept for 30 days and removed when their document’s content is purged. Opening a document checks your access again.</p>
  </section>
}
