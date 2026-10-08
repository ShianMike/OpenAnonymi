import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Bell, Check, CheckCheck, MessageSquare, RefreshCw, ShieldCheck, UserCheck, UserMinus, type LucideIcon } from 'lucide-react'
import type { SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { PageHeader } from '../ui/PageHeader'
import { InlineNotice, RefreshButton } from '../ui/WorkspaceControls'
import { cn } from '../ui/cn'
import { dayKey, dayLabel } from '../workspace/activity/activityPresentation'
import { relativeEdit } from '../workspace/documents/documentPresentation'
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

const icons: Record<Notification['event_code'], LucideIcon> = {
  review_assigned: UserCheck,
  review_unassigned: UserMinus,
  approval_requested: ShieldCheck,
  review_approved: CheckCheck,
  approval_invalidated: RefreshCw,
  comment_added: MessageSquare,
}

export function NotificationList({ items, pending, onRead, now }: {
  items: Notification[]
  pending: string | null
  onRead: (id: string) => void
  now: number
}) {
  const days = new Map<string, Notification[]>()
  for (const item of items) {
    const key = dayKey(item.created_at)
    const rows = days.get(key) ?? []
    rows.push(item)
    days.set(key, rows)
  }
  return <>{Array.from(days, ([key, rows]) => {
    const label = dayLabel(rows[0].created_at, new Date(now).toISOString())
    return <section className="notification-day" key={key} aria-label={`${label} notifications`}>
      <h2 className="notification-day-heading">{label}</h2>
      <ul className="notification-list">{rows.map((item) => {
        const Icon = icons[item.event_code]
        return <li key={item.id} className={cn('notification', item.read_at && 'is-read')}>
          <span className="notification-event-icon" aria-hidden="true"><Icon size={20} strokeWidth={1.6} /></span>
          <div className="notification-details">
            <h3>{messages[item.event_code]}</h3>
            {item.document_available && item.document_id ? <Link to={`/documents/${encodeURIComponent(item.document_id)}/edit`}><span>{item.title || 'Untitled document'}</span><ArrowUpRight size={14} aria-hidden="true" /></Link>
              : <p className="notification-unavailable">Document unavailable. Its access may have changed, or it may have expired or been deleted.</p>}
            <div className="notification-meta">
              {!item.read_at && <span className="notification-unread"><span aria-hidden="true" />Unread</span>}
              <time dateTime={item.created_at} title={new Date(item.created_at).toLocaleString()}>{relativeEdit(item.created_at, now)}</time>
            </div>
          </div>
          <button type="button" className="notification-read" disabled={!!pending}
            aria-disabled={!!item.read_at} tabIndex={item.read_at ? -1 : undefined}
            onClick={() => { if (!item.read_at) onRead(item.id) }}
            aria-label={`${item.read_at ? 'Read' : 'Mark as read'}: ${messages[item.event_code]}`}>
            <Check size={16} aria-hidden="true" />{pending === item.id ? 'Saving…' : item.read_at ? 'Read' : 'Mark as read'}
          </button>
        </li>
      })}</ul>
    </section>
  })}</>
}

export function NotificationsPage({ session }: { session: SessionView }) {
  const [page, setPage] = useState<NotificationPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  const [view, setView] = useState<'all' | 'unread'>('all')
  const [checkedAt, setCheckedAt] = useState(() => Date.now())
  const activeFilter = useRef<HTMLButtonElement>(null)
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
        if (!current.signal.aborted) { setCheckedAt(Date.now()); setPage(result) }
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
      if (view === 'unread' || !id) activeFilter.current?.focus()
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
  const unread = page?.items.filter((item) => !item.read_at).length ?? 0
  const visible = page?.items.filter((item) => view === 'all' || !item.read_at) ?? []
  function refreshInbox() { setAttempt((value) => value + 1); notificationChanged() }
  return <section className="notifications-page" aria-labelledby="notifications-title">
    <PageHeader title="Notifications" titleId="notifications-title" description="Assignments, approvals, and comments across your workspaces."
      action={<div className="notification-heading-actions">
        <RefreshButton label="Refresh notifications" disabled={!!pending || !page} onClick={refreshInbox} />
        <button type="button" className="button-secondary" disabled={!!pending || !unread} onClick={() => void read()}><CheckCheck size={17} aria-hidden="true" />{pending === 'all' ? 'Saving…' : 'Mark all as read'}</button>
      </div>} />
    {notice && <InlineNotice>{notice}</InlineNotice>}
    {error && <InlineNotice error>{error} <RefreshButton label="Retry notification refresh" disabled={!!pending} onClick={refreshInbox} /></InlineNotice>}
    <div className="notification-inbox">
      <div className="notification-toolbar">
        <div className="notification-filters" role="group" aria-label="Notification views">
          <button type="button" aria-pressed={view === 'all'} ref={view === 'all' ? activeFilter : undefined} onClick={() => setView('all')}>All notifications</button>
          <button type="button" aria-pressed={view === 'unread'} ref={view === 'unread' ? activeFilter : undefined} onClick={() => setView('unread')}>Unread{page && <span className="notification-filter-count" aria-label={`${unread} unread in this view`}>{unread}</span>}</button>
        </div>
        <p className="notification-view-count" role="status">{page ? `${visible.length} ${view === 'unread' ? 'unread' : 'updates'}${page.next_cursor ? ' in this view' : ''}` : ''}</p>
      </div>
      {!page && !error && <LoadingState label="Checking notifications…" shape="list" />}
      {page && <>
        {visible.length ? <NotificationList items={visible} pending={pending} onRead={(id) => void read(id)} now={checkedAt} />
          : <div className="notification-empty"><span className="notification-empty-icon">{view === 'unread' ? <CheckCheck size={24} aria-hidden="true" /> : <Bell size={24} aria-hidden="true" />}</span>
            <h2>{view === 'unread' ? page.next_cursor ? 'No unread updates in this view' : 'You’re all caught up' : 'No notifications yet'}</h2>
            <p>{view === 'unread' ? page.next_cursor ? 'Load older notifications to continue through your inbox.' : 'Your earlier updates are still here whenever you need them.' : 'Review assignments, approvals, and comments will appear here.'}</p>
            {view === 'unread' ? <button type="button" className="button-secondary" onClick={() => setView('all')}>View all notifications</button>
              : <Link className="button-secondary" to="/documents">Go to documents <ArrowUpRight size={15} aria-hidden="true" /></Link>}
          </div>}
        {page.next_cursor && <div className="notification-pagination"><button type="button" className="button-secondary" disabled={!!pending} onClick={() => void more()}>{pending === 'more' ? 'Loading…' : 'Load more notifications'}</button></div>}
      </>}
    </div>
    <p className="notification-retention">Updates stay here for 30 days, or until the review’s content is removed. Review access is checked each time you open it.</p>
  </section>
}
