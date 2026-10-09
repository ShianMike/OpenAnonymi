import { useEffect, useState } from 'react'
import { Bell, ShieldCheck } from 'lucide-react'
import type { SessionView } from '../api/client'
import { ChoiceSwitch, InlineNotice, PanelHeading } from '../ui/WorkspaceControls'
import { getNotificationPreferences, updateNotificationPreferences, type NotificationPreferences } from './api'
import './notifications.css'

export function NotificationPreferencesPanel({ session }: { session: SessionView }) {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [requested, setRequested] = useState<boolean | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getNotificationPreferences(controller.signal).then((result) => {
      if (!controller.signal.aborted) { setPreferences(result); setError(null) }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Notification preferences could not be loaded.')
    })
    return () => controller.abort()
  }, [session.user_id, attempt])
  async function change(enabled: boolean) {
    if (pending) return
    setPending(true); setRequested(enabled); setError(null); setNotice(null)
    try {
      setPreferences(await updateNotificationPreferences(enabled ? 'immediate' : 'off', session.csrf_token))
      setNotice('Notification email preference saved.')
    } catch (cause: unknown) { setError(cause instanceof Error ? cause.message : 'The preference could not be saved.') }
    finally { setRequested(null); setPending(false) }
  }
  if (preferences && !preferences.notification_emails_available) return null
  if (!preferences && !error) return null
  return <section className="workspace-panel notification-preferences" aria-busy={pending}>
    <PanelHeading icon={Bell} title="Notification emails" />
    {preferences && <ChoiceSwitch label="Email me about review notifications" description="Assignments, approvals, and comments."
      checked={requested ?? preferences.notification_emails === 'immediate'} disabled={pending} onChange={(value) => void change(value)} />}
    <p className="notification-email-note"><ShieldCheck size={16} aria-hidden="true" /><span>Emails leave out workspace names, document details, and links. Up to 10 per hour; all updates stay in your notification inbox.</span></p>
    {error && <InlineNotice error>{error} <button type="button" disabled={pending} onClick={() => setAttempt((value) => value + 1)}>Reload preference</button></InlineNotice>}
    {notice && <InlineNotice>{notice}</InlineNotice>}
  </section>
}
