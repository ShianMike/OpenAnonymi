import { useState, type FormEvent } from 'react'
import { ArrowRight, Building2, KeyRound, LockKeyhole, Mail, Palette, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { changePassword, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import { EmailVerification } from './EmailVerification'
import { NotificationPreferencesPanel } from '../../notifications/NotificationPreferencesPanel'

export function PasswordPanel({
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
      <section className="account-security workspace-panel">
        <PanelHeading
          icon={KeyRound}
          title="Password"
          description="Choose a strong password for your next sign-in."
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
      </section>
  )
}

export function AccountPanel({ session }: { session: SessionView }) {
  const initials = session.email.split('@')[0].split(/[._+-]/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase()
  return <div className="account-panel-grid">
    <section className="account-overview workspace-panel" aria-labelledby="account-profile-title">
      <div className="account-profile-heading"><span className="account-avatar" aria-hidden="true">{initials}</span>
        <div><h2 id="account-profile-title">Your account</h2><p>Email, security, and workspace access.</p></div>
      </div>
      <div className="account-details-grid">
        <div className="account-profile">
          <div className="account-email"><span><Mail size={16} aria-hidden="true" />Email address</span><strong>{session.email}</strong></div>
          <EmailVerification session={session} />
        </div>
        <section className="account-workspaces" aria-labelledby="account-workspaces-title">
          <div className="account-section-heading"><h3 id="account-workspaces-title">Workspace access</h3><span>{session.memberships.length}</span></div>
          <p>Your role is set separately in each workspace.</p>
          <ul>{session.memberships.map(item => <li key={item.workspace_id}>
            <Building2 size={18} aria-hidden="true" /><div><strong>{item.workspace_name || 'Workspace'}</strong><small>{item.role === 'administrator' ? 'Administrator' : 'Member'}</small></div>
            <Link to={`/?workspace=${encodeURIComponent(item.workspace_id)}`} aria-label={`Open ${item.workspace_name || 'workspace'}`}><ArrowRight size={17} aria-hidden="true" /></Link>
          </li>)}</ul>
        </section>
      </div>
      <div className="account-setting-row">
        <ShieldCheck size={20} aria-hidden="true" /><div><h3>Sign-in protection</h3><p>{session.second_factor_enabled ? 'Two-step verification is enabled.' : 'Add an authenticator for an extra sign-in check.'}</p></div>
        <Link className="button-secondary" to="/settings?section=security">Manage security<ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
      <div className="account-setting-row">
        <Palette size={20} aria-hidden="true" /><div><h3>Display preferences</h3><p>Theme, text size, spacing, and motion on this device.</p></div>
        <Link className="button-secondary" to="/preferences">Preferences<ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
    </section>
    <NotificationPreferencesPanel key={session.user_id} session={session} />
  </div>
}
