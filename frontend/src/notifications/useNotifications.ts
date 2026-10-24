import { useEffect, useRef, useState } from 'react'
import type { SessionView } from '../api/client'
import { getNotifications, getUnreadCount, markAllNotificationsRead, markNotificationRead, notificationChanged, type NotificationPage } from './api'

type Data = { kind: 'loading' } | { kind: 'error'; message: string }
  | { kind: 'ready'; page: NotificationPage; unread: number; checkedAt: number }

export function useNotifications(session: SessionView) {
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const generation = useRef(0)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; generation.current += 1 }
  }, [])
  useEffect(() => {
    let controller: AbortController | undefined
    function refresh() {
      controller?.abort()
      generation.current += 1
      // Clear decrypted titles before every access recheck, including hidden tabs.
      setData({ kind: 'loading' })
      setNotice(''); setActionError('')
      if (document.visibilityState !== 'visible') return
      const current = new AbortController()
      controller = current
      Promise.all([getNotifications(current.signal), getUnreadCount(current.signal)])
        .then(([page, unread]) => { if (!current.signal.aborted) setData({ kind: 'ready', page, unread: unread.count, checkedAt: Date.now() }) })
        .catch(cause => { if (!current.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'Notifications could not be loaded.' }) })
    }
    refresh()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') refresh() }, 60_000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => { controller?.abort(); window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); window.removeEventListener('focus', refresh) }
  }, [session.user_id, attempt])

  async function read(id?: string) {
    if (pending || data.kind === 'error' || !id && data.kind !== 'ready') return false
    const expected = generation.current
    setPending(id ?? 'all'); setActionError(''); setNotice('')
    try {
      if (id) await markNotificationRead(id, session.csrf_token)
      else await markAllNotificationsRead(session.csrf_token)
      notificationChanged()
      const unread = await getUnreadCount()
      if (!mounted.current) return false
      if (generation.current !== expected) { setAttempt(value => value + 1); return false }
      const readAt = new Date().toISOString()
      if (data.kind !== 'ready') setAttempt(value => value + 1)
      setData(current => {
        if (current.kind !== 'ready') return current
        return { ...current, unread: unread.count,
          page: { ...current.page, items: current.page.items.map(item => !item.read_at && (!id || item.id === id) ? { ...item, read_at: readAt } : item) } }
      })
      setNotice(id ? 'Marked as read' : 'All notifications marked as read')
      return true
    } catch (cause) {
      if (mounted.current && generation.current === expected) {
        setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'Read status could not be saved.' })
      }
      return false
    } finally { if (mounted.current) setPending(null) }
  }
  async function loadOlder() {
    if (pending || data.kind !== 'ready' || !data.page.next_cursor) return
    const expected = generation.current
    setPending('more'); setActionError(''); setNotice('')
    try {
      const next = await getNotifications(undefined, data.page.next_cursor)
      if (!mounted.current || generation.current !== expected) return
      setData(current => current.kind !== 'ready' ? current : { ...current,
        page: { next_cursor: next.next_cursor, items: [...current.page.items, ...next.items.filter(row => !current.page.items.some(item => item.id === row.id))] } })
    } catch (cause) {
      if (mounted.current && generation.current === expected) setActionError(cause instanceof Error ? cause.message : 'Older notifications could not be loaded.')
    } finally { if (mounted.current) setPending(null) }
  }
  function refresh() { setNotice(''); setActionError(''); setAttempt(value => value + 1); notificationChanged() }
  return { data, pending, notice, actionError, read, loadOlder, refresh }
}
