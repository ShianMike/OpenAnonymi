import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { updateWorkspaceSettings, type SessionView, type WorkspaceSettingsView } from '../../api/client'
import { ChoiceSwitch, InlineNotice } from '../../ui/WorkspaceControls'
import { SettingsConfirmation } from './SettingsConfirmation'
import { settingsHref } from './settingsNavigation'

export function WorkspaceSecurityPanel({ settings, session, onSaved, onReload, onRequestFailed }: {
  settings: WorkspaceSettingsView; session: SessionView; onSaved: (settings: WorkspaceSettingsView) => void
  onReload: () => void; onRequestFailed: (cause: unknown) => void
}) {
  const [requireFactor, setRequireFactor] = useState(settings.require_second_factor)
  const [approval, setApproval] = useState(settings.approval_policy === 'always')
  const [pending, setPending] = useState(false)
  const [review, setReview] = useState<'save' | 'reload' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [conflict, setConflict] = useState(false)
  const saveButton = useRef<HTMLButtonElement>(null)
  const changed = requireFactor !== settings.require_second_factor || approval !== (settings.approval_policy === 'always')
  async function save() {
    if (pending || !changed || conflict) return
    setPending(true); setError(''); setNotice('')
    try {
      const updated = await updateWorkspaceSettings(settings.id, settings.settings_version, settings.content_retention_days,
        settings.activity_retention_days, session.csrf_token, requireFactor, approval ? 'always' : 'owner_choice')
      onSaved(updated); setRequireFactor(updated.require_second_factor); setApproval(updated.approval_policy === 'always'); setReview(null)
      setNotice('Workspace policies saved.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Workspace policies could not be saved.')
      setConflict(true); setReview(null); onRequestFailed(cause)
    } finally { setPending(false) }
  }
  function reset() { setRequireFactor(settings.require_second_factor); setApproval(settings.approval_policy === 'always'); if (!conflict) setError(''); setNotice('') }
  return <>
    <form className="settings-policies-form" onSubmit={event => { event.preventDefault(); setReview('save') }}>
      <section className="settings-section" aria-labelledby="workspace-signin-title"><header className="settings-section-heading"><h3 id="workspace-signin-title">Sign-in requirement</h3><p>Apply a consistent sign-in policy to workspace members.</p></header>
        <ChoiceSwitch label="Require two-step verification" description="Members without an authenticator must set one up at their next sign-in, within 12 hours." checked={requireFactor}
          disabled={pending || (!settings.require_second_factor && !session.second_factor_enabled)} disabledReason={!session.second_factor_enabled && !settings.require_second_factor ? 'Enable two-step verification on your account first.' : undefined} onChange={value => { setRequireFactor(value); setNotice('') }} />
        <p className="settings-help">{settings.members_without_second_factor} active {settings.members_without_second_factor === 1 ? 'member has' : 'members have'} no two-step verification.</p>
        {!session.second_factor_enabled && !settings.require_second_factor && <Link className="settings-text-link" to={settingsHref('security', settings.id)}>Set up your authenticator first</Link>}
      </section>
      <section className="settings-section" aria-labelledby="workspace-approval-title"><header className="settings-section-heading"><h3 id="workspace-approval-title">Independent review</h3><p>Control whether another person must approve a review before it can be shared.</p></header>
        <ChoiceSwitch label="Require reviewer approval for every export" description="An active assigned reviewer must approve the exact confirmed version before it can be copied or downloaded." checked={approval} disabled={pending} onChange={value => { setApproval(value); setNotice('') }} />
        {approval && settings.active_member_count < 2 && <InlineNotice actions={<Link className="settings-button" to={`/members?workspace=${encodeURIComponent(settings.id)}`}>Manage members</Link>}>This workspace has one active member. Add another member before reviews can receive independent approval.</InlineNotice>}
        <p className="settings-help">The policy is checked for each output. Existing review versions and reviewer assignments are kept.</p>
      </section>
      {error && <InlineNotice error title="Check the saved workspace policies" actions={<button type="button" className="settings-button" disabled={pending} onClick={() => setReview('reload')}>Reload saved policies</button>}><p>{error}</p><p>Your edits are still here. Reload the saved values before trying to save again.</p></InlineNotice>}{notice && <InlineNotice>{notice}</InlineNotice>}
      <footer className="settings-save-bar"><span>{conflict ? 'Reload required' : changed ? 'Unsaved changes' : 'Up to date'}</span><div>{changed && <button type="button" className="settings-button" disabled={pending} onClick={reset}>Reset</button>}<button ref={saveButton} type="submit" className="settings-button settings-primary" disabled={pending || !changed || conflict}>Review changes</button></div></footer>
    </form>
    <SettingsConfirmation open={review !== null} title={review === 'reload' ? 'Discard edits and reload?' : 'Save workspace policies?'} description={review === 'reload' ? 'Your unsaved policy edits will be replaced with the latest saved settings.' : `These requirements apply to members of ${settings.name}.`} pending={pending} dirty={changed} confirmLabel={review === 'reload' ? 'Discard and reload' : 'Save policies'} danger={review === 'reload' || (settings.require_second_factor && !requireFactor) || (settings.approval_policy === 'always' && !approval)} returnFocus={saveButton} onCancel={() => setReview(null)} onConfirm={() => { if (review === 'reload') onReload(); else void save() }}>
      {review === 'save' && <dl className="settings-change-summary">{requireFactor !== settings.require_second_factor && <div><dt>Two-step verification</dt><dd>{settings.require_second_factor ? 'Required' : 'Optional'} → <strong>{requireFactor ? 'Required' : 'Optional'}</strong></dd></div>}{approval !== (settings.approval_policy === 'always') && <div><dt>Reviewer approval</dt><dd>{settings.approval_policy === 'always' ? 'Every export' : 'Owner decides'} → <strong>{approval ? 'Every export' : 'Owner decides'}</strong></dd></div>}</dl>}
      {review === 'save' && approval && settings.active_member_count < 2 && <p className="settings-help">Exports will require another active member to be assigned and approve the confirmed version.</p>}
    </SettingsConfirmation>
  </>
}
