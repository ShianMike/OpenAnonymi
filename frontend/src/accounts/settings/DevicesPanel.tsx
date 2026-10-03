import { useEffect, useState } from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { Monitor } from 'lucide-react'
import { getDevices, revokeDevice, revokeOtherDevices, type DeviceView } from '../../api/client'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'

const method: Record<string, string> = { password: 'Password', password_totp: 'Authenticator', password_backup_code: 'Backup code', enrollment: 'Authenticator setup' }
export function DevicesPanel({ csrfToken, onSignedOut }: { csrfToken: string; onSignedOut: () => void }) {
  const [devices, setDevices] = useState<DeviceView[] | null>(null)
  const [choice, setChoice] = useState<DeviceView | 'others' | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getDevices(controller.signal).then((value) => { if (!controller.signal.aborted) setDevices(value) })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Devices could not be loaded.') })
    return () => controller.abort()
  }, [attempt])
  async function confirm() {
    if (!choice || pending) return
    setPending(true); setError(null)
    try {
      if (choice === 'others') await revokeOtherDevices(csrfToken)
      else await revokeDevice(choice.id, csrfToken)
      if (choice !== 'others' && choice.current) { onSignedOut(); return }
      setNotice(choice === 'others' ? 'Other sessions signed out.' : 'Session signed out.')
      setChoice(null); setAttempt((value) => value + 1)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The session could not be signed out.') }
    finally { setPending(false) }
  }
  return (
    <section className="workspace-panel">
      <PanelHeading icon={Monitor} title="Signed-in devices" description="Each entry is an active session. Signing it out takes effect immediately." />
      {error && !choice && <InlineNotice error>{error}</InlineNotice>}
      {notice && <InlineNotice>{notice}</InlineNotice>}
      {!devices && !error && <p role="status">Loading devices…</p>}
      {devices && <ul className="security-device-list">{devices.map((device) => <li key={device.id}>
        <div><strong>{device.device_label}{device.current && <span className="security-current">Current session</span>}</strong>
          <small>{method[device.auth_method] ?? 'Sign-in'} · Signed in {new Date(device.created_at).toLocaleString()}</small>
          <small>Last active {new Date(device.last_seen_at).toLocaleString()}</small>
        </div>
        <button type="button" className="quiet-button" onClick={() => { setChoice(device); setError(null) }}>Sign out{device.current ? ' this session' : ' session'}</button>
      </li>)}</ul>}
      {devices?.length === 100 && <small>Showing your current session and the 99 most recently active other sessions.</small>}
      <div className="security-actions">
        <button type="button" className="quiet-button" disabled={pending || !devices?.some((item) => !item.current)} onClick={() => { setChoice('others'); setError(null) }}>Sign out all other sessions</button>
        <button type="button" className="quiet-button" disabled={pending} onClick={() => { setError(null); setAttempt((value) => value + 1) }}>Refresh devices</button>
      </div>
      <AlertDialog.Root open={choice !== null} onOpenChange={(open) => { if (!open && !pending) setChoice(null) }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="workspace-dialog-overlay" />
          <AlertDialog.Content className="workspace-dialog" onEscapeKeyDown={(event) => { if (pending) event.preventDefault() }}>
            <AlertDialog.Title>{choice === 'others' ? 'Sign out all other sessions?' : 'Sign out this session?'}</AlertDialog.Title>
            <AlertDialog.Description>{choice === 'others' ? 'Other devices will need to sign in again. This session stays open.' : choice?.current ? 'You will need to sign in again on this device.' : 'This device will need to sign in again.'}</AlertDialog.Description>
            {error && <InlineNotice error>{error}</InlineNotice>}
            <div className="dialog-actions"><AlertDialog.Cancel disabled={pending}>Cancel</AlertDialog.Cancel><button type="button" disabled={pending} onClick={() => void confirm()}>{pending ? 'Signing out…' : 'Confirm sign out'}</button></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  )
}
