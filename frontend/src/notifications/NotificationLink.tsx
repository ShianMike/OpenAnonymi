import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { getUnreadCount } from './api'
import './notifications.css'

export function NotificationLink({ userId }: { userId: string }) {
  const [count, setCount] = useState<number | null>(null)
  useEffect(() => {
    let controller: AbortController | undefined
    let pending = false
    function refresh() {
      if (document.visibilityState !== 'visible') {
        controller?.abort()
        pending = false
        setCount(null)
        return
      }
      if (pending) return
      controller = new AbortController()
      const current = controller
      pending = true
      getUnreadCount(current.signal).then((result) => {
        if (!current.signal.aborted) setCount(result.count)
      }).catch(() => {
        if (!current.signal.aborted) setCount(null)
      }).finally(() => {
        if (controller === current) pending = false
      })
    }
    refresh()
    const timer = window.setInterval(refresh, 60_000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    window.addEventListener('openanonymi:notifications-changed', refresh)
    return () => {
      controller?.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('openanonymi:notifications-changed', refresh)
    }
  }, [userId])
  return <Link to="/notifications" className="notification-link" aria-label={`Notifications${count != null ? `, ${count} unread` : ''}`}>
    <Bell size={18} aria-hidden="true" />
    {!!count && <span className="notification-count" aria-hidden="true">{count > 99 ? '99+' : count}</span>}
  </Link>
}
