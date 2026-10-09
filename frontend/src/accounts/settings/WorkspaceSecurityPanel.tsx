import { useState } from 'react'
import { ChevronDown, ShieldCheck } from 'lucide-react'
import { updateWorkspaceSettings, type SessionView, type WorkspaceSettingsView } from '../../api/client'
import { ChoiceSwitch, InlineNotice, RefreshButton } from '../../ui/WorkspaceControls'

export function WorkspaceSecurityPanel({ settings, session, onSaved, onReload }: {
  settings: WorkspaceSettingsView; session: SessionView;
  onSaved: (settings: WorkspaceSettingsView) => void; onReload: () => void;
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [requested, setRequested] = useState<boolean | null>(null)
  const [approvalRequested, setApprovalRequested] = useState<boolean | null>(null)
  async function change(required: boolean) {
    setRequested(required); setPending(true); setError(null); setNotice(null)
    try {
      const updated = await updateWorkspaceSettings(settings.id, settings.settings_version,
        settings.content_retention_days, settings.activity_retention_days, session.csrf_token, required)
      onSaved(updated); setNotice('Workspace security requirement saved.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The requirement could not be saved.') }
    finally { setRequested(null); setPending(false) }
  }
  async function changeApproval(required: boolean) {
    setApprovalRequested(required); setPending(true); setError(null); setNotice(null)
    try {
      const updated = await updateWorkspaceSettings(settings.id, settings.settings_version,
        settings.content_retention_days, settings.activity_retention_days, session.csrf_token,
        undefined, required ? 'always' : 'owner_choice')
      onSaved(updated); setNotice('Workspace approval policy saved.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The approval policy could not be saved.') }
    finally { setApprovalRequested(null); setPending(false) }
  }
  return (
    <details className="workspace-panel workspace-security settings-details">
      <summary><ShieldCheck size={19} aria-hidden="true" /><span><strong>Workspace security</strong><small>Authenticator and approval requirements for this workspace.</small></span><ChevronDown size={16} aria-hidden="true" /></summary>
      <div className="settings-details-body">
      <p>{settings.members_without_second_factor} active {settings.members_without_second_factor === 1 ? 'member has' : 'members have'} no two-step verification.</p>
      <ChoiceSwitch label="Require two-step verification" checked={requested ?? settings.require_second_factor}
        disabled={pending || (!settings.require_second_factor && !session.second_factor_enabled)} onChange={(value) => void change(value)} />
      <p>Members without two-step verification must set it up when they next sign in (within 12 hours).</p>
      {!session.second_factor_enabled && !settings.require_second_factor && <small>Enable two-step verification on your account first to turn on this requirement.</small>}
      <ChoiceSwitch label="Require reviewer approval for every export"
        description="Every document needs an active assigned reviewer to approve its exact confirmed version before copying or downloading."
        checked={approvalRequested ?? settings.approval_policy === 'always'} disabled={pending}
        onChange={(value) => void changeApproval(value)} />
      {(approvalRequested ?? settings.approval_policy === 'always') && settings.active_member_count < 2 &&
        <p role="alert">This workspace has one active member. Add another member before any document can receive independent approval.</p>}
      <p className="field-note">The policy is checked when each output is generated. Changing it keeps existing review versions and reviewer assignments.</p>
      {error && <InlineNotice error>{error}<RefreshButton label="Reload workspace settings" disabled={pending} onClick={onReload} /></InlineNotice>}
      {notice && <InlineNotice>{notice}</InlineNotice>}
      </div>
    </details>
  )
}
