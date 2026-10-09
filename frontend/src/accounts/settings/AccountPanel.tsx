import { useState, type FormEvent } from 'react'
import { ArrowRight, Building2, KeyRound, LockKeyhole, Palette, Search, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { changePassword, type SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import { EmailVerification } from './EmailVerification'
import { NotificationPreferencesPanel } from '../../notifications/NotificationPreferencesPanel'
import { ListPagination } from '../../ui/ListPagination'
import { pageWindow } from '../../ui/pagination'

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

export function AccountPanel({ session, onSessionChanged }: {
  session: SessionView; onSessionChanged: (session: SessionView) => void
}) {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const memberships = session.memberships.filter(item => `${item.workspace_name} ${item.role}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  const range = pageWindow(memberships.length, page, 3)
  const initials = session.email.split('@')[0].split(/[._+-]/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase()
  return <div className="account-panel-grid">
    <div className="account-column">
      <section className="account-overview workspace-panel" aria-labelledby="account-profile-title">
        <div className="account-profile-heading"><span className="account-avatar" aria-hidden="true">{initials}</span>
          <div><h2 id="account-profile-title">Your account</h2><p>Your sign-in email and verification status.</p></div>
        </div>
        <div className="account-profile">
          <EmailVerification session={session} onVerified={onSessionChanged} />
        </div>
      </section>
      <div className="account-shortcuts">
        <Link className="account-setting-link" to="/settings?section=security" aria-label="Manage security">
          <span className="account-shortcut-icon"><ShieldCheck size={20} aria-hidden="true" /></span><div><h3>Sign-in protection</h3><p>{session.second_factor_enabled ? 'Two-step verification is enabled.' : 'Add an authenticator for an extra sign-in check.'}</p><span>Manage security<ArrowRight size={15} aria-hidden="true" /></span></div>
        </Link>
        <Link className="account-setting-link" to="/preferences" aria-label="Preferences">
          <span className="account-shortcut-icon"><Palette size={20} aria-hidden="true" /></span><div><h3>Display preferences</h3><p>Theme, text size, spacing, and motion on this device.</p><span>Preferences<ArrowRight size={15} aria-hidden="true" /></span></div>
        </Link>
      </div>
    </div>
    <div className="account-column">
      <section className="account-workspaces workspace-panel" aria-labelledby="account-workspaces-title">
        <div className="account-workspaces-heading">
          <div className="account-section-heading"><h2 id="account-workspaces-title">Workspace access</h2><span>{session.memberships.length}</span></div>
          <p>Your role is set separately in each workspace.</p>
        </div>
        {session.memberships.length > 3 && <GlassInput type="search" icon={Search} aria-label="Find a workspace" placeholder="Find a workspace…"
          value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} />}
        <ul>{memberships.slice(range.start, range.end).map(item => <li key={item.workspace_id}>
          <Link to={`/?workspace=${encodeURIComponent(item.workspace_id)}`} aria-label={`Open ${item.workspace_name || 'workspace'}`}>
            <span className="account-workspace-icon"><Building2 size={18} aria-hidden="true" /></span><div><strong>{item.workspace_name || 'Workspace'}</strong><small>{item.role === 'administrator' ? 'Administrator' : 'Member'}</small></div>
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </li>)}</ul>
        {!memberships.length && <p className="account-workspaces-empty" role="status">{search.trim() ? 'No matching workspaces. Try another name or role.' : 'You have no active workspace access.'}</p>}
        {session.memberships.length > 3 && <ListPagination page={range.page} total={memberships.length} pageSize={3} label="Workspaces"
          onPrevious={() => setPage(range.page - 1)} onNext={() => setPage(range.page + 1)} />}
      </section>
      <NotificationPreferencesPanel key={session.user_id} session={session} />
    </div>
  </div>
}
