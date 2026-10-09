import { get, sendJson } from '../api/client'
import type { components } from '../api/schema'

export type Notification = components['schemas']['NotificationView']
export type NotificationPage = components['schemas']['NotificationPage']
export type NotificationPreferences = components['schemas']['NotificationPreferences']

export function getNotifications(signal?: AbortSignal, cursor?: string): Promise<NotificationPage> {
  return get(`/notifications${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`, signal)
}

export function getUnreadCount(signal?: AbortSignal): Promise<components['schemas']['UnreadCount']> {
  return get('/notifications/unread-count', signal)
}

export function markNotificationRead(id: string, csrf: string): Promise<void> {
  return sendJson('POST', `/notifications/${encodeURIComponent(id)}/read`, undefined, csrf)
}

export function markAllNotificationsRead(csrf: string): Promise<components['schemas']['ReadAllResult']> {
  return sendJson('POST', '/notifications/read-all', undefined, csrf)
}

export function getNotificationPreferences(signal?: AbortSignal): Promise<NotificationPreferences> {
  return get('/auth/preferences', signal)
}

export function updateNotificationPreferences(value: NotificationPreferences['notification_emails'], csrf: string): Promise<NotificationPreferences> {
  return sendJson('PUT', '/auth/preferences', { notification_emails: value }, csrf)
}

export function notificationChanged() {
  window.dispatchEvent(new Event('openanonymi:notifications-changed'))
}
