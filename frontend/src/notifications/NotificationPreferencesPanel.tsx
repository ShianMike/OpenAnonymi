import { useEffect, useState } from 'react'
import { Mail, ShieldCheck } from 'lucide-react'
import type { SessionView } from '../api/client'
import { ChoiceSwitch, InlineNotice } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
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
  return <section className="notification-preferences" aria-label="Delivery channels" aria-busy={pending}>
    <div className="notification-preferences-heading"><Mail size={18} strokeWidth={1.5} aria-hidden="true" /><div><h3>Email updates</h3><p>Get review notifications in your email inbox.</p></div></div>
    {!preferences && !error && <LoadingState label="Loading your preferences…" compact />}
    {preferences && <ChoiceSwitch label="Send me email updates" description={preferences.notification_emails_available ? 'Assignments, approvals and comments.' : 'Email delivery isn’t available on this installation.'}
      checked={requested ?? preferences.notification_emails === 'immediate'} disabled={pending || !preferences.notification_emails_available} onChange={(value) => void change(value)} />}
    <p className="notification-email-note"><ShieldCheck size={15} aria-hidden="true" /><span>Email messages leave out document details and links. Up to 10 per hour. All updates remain in your notification inbox.</span></p>
    {error && <InlineNotice error title="Check your email preference" actions={<button type="button" disabled={pending} onClick={() => { setPreferences(null); setError(null); setAttempt(value => value + 1) }}>Reload preference</button>}>{error}</InlineNotice>}
    {notice && <InlineNotice>{notice}</InlineNotice>}
  </section>
}
