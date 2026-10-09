import { useEffect, useRef, useState } from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { ChevronDown, Monitor } from 'lucide-react'
import { getDevices, revokeDevice, revokeOtherDevices, type DeviceView } from '../../api/client'
import { InlineNotice, RefreshButton } from '../../ui/WorkspaceControls'

const method: Record<string, string> = { password: 'Password', password_totp: 'Authenticator', password_backup_code: 'Backup code', enrollment: 'Authenticator setup' }
export function DevicesPanel({ csrfToken, onSignedOut }: { csrfToken: string; onSignedOut: () => void }) {
  const [devices, setDevices] = useState<DeviceView[] | null>(null)
  const [choice, setChoice] = useState<DeviceView | 'others' | null>(null)
  const [pending, setPending] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const summary = useRef<HTMLElement | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getDevices(controller.signal).then((value) => { if (!controller.signal.aborted) setDevices(value) })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Devices could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setFetching(false) })
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
      setChoice(null); setFetching(true); setAttempt((value) => value + 1)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The session could not be signed out.') }
    finally { setPending(false) }
  }
  return (
    <details className="workspace-panel devices-panel settings-details">
      <summary ref={summary}><Monitor size={19} aria-hidden="true" /><span><strong>Signed-in devices</strong><small>
        {devices ? `${devices.length} active session${devices.length === 1 ? '' : 's'} · Review or sign out a device.` : 'Review your active sessions.'}
      </small></span><ChevronDown size={16} aria-hidden="true" /></summary>
      <div className="settings-details-body">
      <p className="field-note">Signing out a session takes effect immediately.</p>
      {error && !choice && <InlineNotice error>{error}</InlineNotice>}
      {notice && <InlineNotice>{notice}</InlineNotice>}
      {!devices && !error && <p role="status">Loading devices…</p>}
      {devices && <ul className="security-device-list">{devices.map((device) => <li key={device.id}>
        <div><strong>{device.device_label}{device.current && <span className="security-current">Current session</span>}</strong>
          <small>{method[device.auth_method] ?? 'Sign-in'} · Signed in {new Date(device.created_at).toLocaleString()}</small>
          <small>Last active {new Date(device.last_seen_at).toLocaleString()}</small>
        </div>
        <button type="button" className="quiet-button" onClick={event => { trigger.current = event.currentTarget; setChoice(device); setError(null) }}>Sign out{device.current ? ' this session' : ' session'}</button>
      </li>)}</ul>}
      {devices?.length === 100 && <small>Showing your current session and the 99 most recently active other sessions.</small>}
      <div className="security-actions">
        <button type="button" className="quiet-button" disabled={pending || !devices?.some((item) => !item.current)} onClick={event => { trigger.current = event.currentTarget; setChoice('others'); setError(null) }}>Sign out all other sessions</button>
        <RefreshButton label="Refresh devices" disabled={pending} pending={fetching} onClick={() => { setError(null); setFetching(true); setAttempt((value) => value + 1) }} />
      </div>
      </div>
      <AlertDialog.Root open={choice !== null} onOpenChange={(open) => { if (!open && !pending) setChoice(null) }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="workspace-dialog-overlay" />
          <AlertDialog.Content className="workspace-dialog" onEscapeKeyDown={(event) => { if (pending) event.preventDefault() }}
            onCloseAutoFocus={event => { event.preventDefault(); (trigger.current?.isConnected ? trigger.current : summary.current)?.focus() }}>
            <AlertDialog.Title>{choice === 'others' ? 'Sign out all other sessions?' : 'Sign out this session?'}</AlertDialog.Title>
            <AlertDialog.Description>{choice === 'others' ? 'Other devices will need to sign in again. This session stays open.' : choice?.current ? 'You will need to sign in again on this device.' : 'This device will need to sign in again.'}</AlertDialog.Description>
            {error && <InlineNotice error>{error}</InlineNotice>}
            <div className="dialog-actions"><AlertDialog.Cancel disabled={pending}>Cancel</AlertDialog.Cancel><button type="button" disabled={pending} onClick={() => void confirm()}>{pending ? 'Signing out…' : 'Confirm sign out'}</button></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </details>
  )
}
