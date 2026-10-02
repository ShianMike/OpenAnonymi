import { useState, type FormEvent } from 'react'
import { KeyRound, LockKeyhole, Mail, ShieldCheck } from 'lucide-react'
import { changePassword, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'

export function AccountPanel({
  session,
  onPasswordChanged,
}: {
  session: SessionView
  onPasswordChanged: () => void
}) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function save(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      await changePassword(currentPassword, newPassword, session.csrf_token)
      setCurrentPassword('')
      setNewPassword('')
      onPasswordChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Password could not be changed.')
    } finally {
      setPending(false)
    }
  }
  return (
    <div className="account-panel-grid">
      <div className="account-profile workspace-panel">
        <span className="account-avatar" aria-hidden="true">
          {session.email.slice(0, 2).toUpperCase()}
        </span>
        <h2>Your account</h2>
        <p>Your own space to review with care.</p>
        <div className="account-email">
          <span>
            <Mail size={14} aria-hidden="true" /> Email address
          </span>
          <strong>{session.email}</strong>
        </div>
        <div className="account-privacy-note">
          <ShieldCheck size={18} strokeWidth={1.5} aria-hidden="true" />
          <p>Your documents and decisions stay connected to this account.</p>
        </div>
      </div>
      <div className="account-security workspace-panel">
        <PanelHeading
          icon={KeyRound}
          title="Password & security"
          description="Keep access to your account in your hands."
        />
        <form className="account-password-form" onSubmit={save}>
          <div>
            <label className="field-label" htmlFor="current-password">
              Current password
            </label>
            <GlassInput
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              disabled={pending}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="changed-password">
              New password
            </label>
            <GlassInput
              id="changed-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              disabled={pending}
              aria-describedby="new-password-hint"
            />
            <p className="field-note" id="new-password-hint">
              Use at least 12 characters.
            </p>
          </div>
          {error && <InlineNotice error>{error}</InlineNotice>}
          <div className="settings-save-row">
            <p>
              <LockKeyhole size={14} aria-hidden="true" /> Changing your password signs you out on every
              device.
            </p>
            <button type="submit" disabled={pending || !currentPassword || newPassword.length < 12}>
              {pending ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
