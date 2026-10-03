import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { updateWorkspaceSettings, type SessionView, type WorkspaceSettingsView } from '../../api/client'
import { ChoiceSwitch, InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'

export function WorkspaceSecurityPanel({ settings, session, onSaved, onReload }: {
  settings: WorkspaceSettingsView; session: SessionView;
  onSaved: (settings: WorkspaceSettingsView) => void; onReload: () => void;
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [requested, setRequested] = useState<boolean | null>(null)
  async function change(required: boolean) {
    setRequested(required); setPending(true); setError(null); setNotice(null)
    try {
      const updated = await updateWorkspaceSettings(settings.id, settings.settings_version,
        settings.content_retention_days, settings.activity_retention_days, session.csrf_token, required)
      onSaved(updated); setNotice('Workspace security requirement saved.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The requirement could not be saved.') }
    finally { setRequested(null); setPending(false) }
  }
  return (
    <section className="workspace-panel">
      <PanelHeading icon={ShieldCheck} title="Workspace security" description="The requirement applies to every active member of the selected workspace." />
      <p>{settings.members_without_second_factor} active {settings.members_without_second_factor === 1 ? 'member has' : 'members have'} no two-step verification.</p>
      <ChoiceSwitch label="Require two-step verification" checked={requested ?? settings.require_second_factor}
        disabled={pending || (!settings.require_second_factor && !session.second_factor_enabled)} onChange={(value) => void change(value)} />
      <p>Members without two-step verification must set it up when they next sign in (within 12 hours).</p>
      {!session.second_factor_enabled && !settings.require_second_factor && <small>Enable two-step verification on your account first to turn on this requirement.</small>}
      {error && <InlineNotice error>{error}<button type="button" onClick={onReload}>Reload workspace settings</button></InlineNotice>}
      {notice && <InlineNotice>{notice}</InlineNotice>}
    </section>
  )
}
