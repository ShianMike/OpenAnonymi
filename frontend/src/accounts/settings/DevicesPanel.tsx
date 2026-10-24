import { useEffect, useRef, useState } from 'react'
import { Monitor } from 'lucide-react'
import { getDevices, revokeDevice, revokeOtherDevices, type DeviceView } from '../../api/client'
import { InlineNotice, RefreshButton } from '../../ui/WorkspaceControls'
import { LoadingState } from '../../loading/LoadingState'
import { ListPagination } from '../../ui/ListPagination'
import { pageWindow } from '../../ui/pagination'
import { SettingsConfirmation } from './SettingsConfirmation'

const method: Record<string, string> = { password: 'Password', password_totp: 'Authenticator', password_backup_code: 'Backup code', enrollment: 'Authenticator setup' }
export function DevicesPanel({ csrfToken, onSignedOut }: { csrfToken: string; onSignedOut: () => void }) {
  const [devices, setDevices] = useState<DeviceView[] | null>(null)
  const [choice, setChoice] = useState<DeviceView | 'others' | null>(null)
  const [pending, setPending] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [page, setPage] = useState(0)
  const trigger = useRef<HTMLElement | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    getDevices(controller.signal).then(value => { if (!controller.signal.aborted) setDevices(value) })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Sessions could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setFetching(false) })
    return () => controller.abort()
  }, [attempt])
  function reload() { setDevices(null); setError(''); setFetching(true); setAttempt(value => value + 1) }
  async function confirm() {
    if (!choice || pending) return
    setPending(true); setError('')
    try {
      if (choice === 'others') await revokeOtherDevices(csrfToken)
      else await revokeDevice(choice.id, csrfToken)
      if (choice !== 'others' && choice.current) { onSignedOut(); return }
      setNotice(choice === 'others' ? 'Other sessions signed out. This session stays open.' : 'Session signed out.')
      trigger.current = heading.current; setChoice(null); reload()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The session could not be signed out.') }
    finally { setPending(false) }
  }
  const range = pageWindow(devices?.length ?? 0, page, 10)
  return <section className="settings-section settings-devices" aria-labelledby="settings-devices-title" aria-busy={fetching}>
    <header className="settings-section-heading settings-section-tools"><div><h3 ref={heading} tabIndex={-1} id="settings-devices-title">Active sessions{devices && <span className="settings-count">{devices.length}</span>}</h3><p>Each entry is a sign-in session. A browser can appear more than once.</p></div><RefreshButton label="Refresh sessions" pending={fetching} disabled={pending} onClick={reload} /></header>
    {error && !choice && <InlineNotice error title="Sessions couldn’t be loaded" actions={<button type="button" className="settings-button" disabled={fetching} onClick={reload}>Try again</button>}>{error}</InlineNotice>}{notice && <InlineNotice>{notice}</InlineNotice>}
    {!devices && !error && <LoadingState label="Loading active sessions…" compact />}
    {devices && <ul className="settings-device-list">{devices.slice(range.start, range.end).map(device => <li key={device.id}>
      <Monitor size={19} aria-hidden="true" /><div><strong>{device.device_label}</strong>{device.current && <span className="settings-status" data-enabled="true">This session</span>}<p>{method[device.auth_method] ?? 'Sign-in'} · Signed in <time dateTime={device.created_at}>{new Date(device.created_at).toLocaleString()}</time></p><small>Last active <time dateTime={device.last_seen_at}>{new Date(device.last_seen_at).toLocaleString()}</time></small></div>
      <button type="button" className="settings-button" disabled={pending || fetching} onClick={event => { trigger.current = event.currentTarget; setChoice(device); setError('') }}>{device.current ? 'Sign out this session' : 'Sign out'}</button>
    </li>)}</ul>}
    {devices?.length === 0 && <p className="settings-help">No active sessions were returned. Refresh to check again.</p>}
    {(devices?.length ?? 0) > 10 && <ListPagination page={range.page} total={devices!.length} pageSize={10} label="Sessions" onPrevious={() => { setPage(range.page - 1); heading.current?.focus() }} onNext={() => { setPage(range.page + 1); heading.current?.focus() }} />}
    {devices?.length === 100 && <p className="settings-help">Showing this session and the 99 most recently active other sessions.</p>}
    <div className="settings-form-actions"><button type="button" className="settings-button settings-danger" disabled={pending || fetching || !devices?.some(item => !item.current)} onClick={event => { trigger.current = event.currentTarget; setChoice('others'); setError('') }}>Sign out all other sessions</button></div>
    <SettingsConfirmation open={choice !== null} title={choice === 'others' ? 'Sign out all other sessions?' : choice?.current ? 'Sign out this session?' : 'Sign out session?'} description={choice === 'others' ? 'Other sessions will end immediately and need to sign in again. This session stays open.' : choice?.current ? 'You will be signed out here and need to sign in again to continue.' : 'This session will end immediately. It will need to sign in again.'} pending={pending} pendingLabel="Signing out…" error={error} confirmLabel="Confirm sign out" danger onCancel={() => setChoice(null)} onConfirm={() => void confirm()} returnFocus={trigger}>
      {choice && choice !== 'others' && <p className="settings-confirmation-target">{choice.device_label}<small>Signed in {new Date(choice.created_at).toLocaleString()}</small></p>}
    </SettingsConfirmation>
  </section>
}
