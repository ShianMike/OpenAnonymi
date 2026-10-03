import { useState, type FormEvent } from 'react'
import { Activity, Clock3, FileText, RotateCcw } from 'lucide-react'
import { updateWorkspaceSettings, type WorkspaceSettingsView } from '../../api/client'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import { CleanupHealthPanel } from './CleanupHealthPanel'

export function RetentionPanel({
  settings,
  csrfToken,
  onSaved,
  onReload,
}: {
  settings: WorkspaceSettingsView
  csrfToken: string
  onSaved: (value: WorkspaceSettingsView) => void
  onReload: () => void
}) {
  const [contentDays, setContentDays] = useState(String(settings.content_retention_days))
  const [activityDays, setActivityDays] = useState(String(settings.activity_retention_days))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const changed =
    Number(contentDays) !== settings.content_retention_days ||
    Number(activityDays) !== settings.activity_retention_days
  async function save(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await updateWorkspaceSettings(
        settings.id,
        settings.settings_version,
        Number(contentDays),
        Number(activityDays),
        csrfToken,
      )
      onSaved(updated)
      setContentDays(String(updated.content_retention_days))
      setActivityDays(String(updated.activity_retention_days))
      setNotice('Defaults saved. Existing document expiry dates stay the same.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Defaults could not be saved.')
    } finally {
      setPending(false)
    }
  }
  return (
    <div className="retention-panel workspace-panel">
      <PanelHeading
        icon={Clock3}
        title="Keep what you need. Let the rest go."
        description="Set how long content and activity remain in this workspace."
      />
      <form onSubmit={save}>
        <div className="retention-cards">
          <div className="retention-setting">
            <span className="retention-setting-icon">
              <FileText size={21} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <label htmlFor="content-days">Document content</label>
            <p>The default lifetime for new reviews.</p>
            <div className="retention-number">
              <input
                id="content-days"
                aria-label="Document content days"
                type="number"
                min={1}
                max={30}
                required
                value={contentDays}
                onChange={(event) => setContentDays(event.target.value)}
                disabled={pending}
              />
              <span>days</span>
            </div>
            <span className="field-note">Choose from 1 to 30 days</span>
          </div>
          <div className="retention-setting">
            <span className="retention-setting-icon">
              <Activity size={21} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <label htmlFor="activity-days">Activity records</label>
            <p>A history of actions, without document text.</p>
            <div className="retention-number">
              <input
                id="activity-days"
                aria-label="Activity days"
                type="number"
                min={1}
                max={365}
                required
                value={activityDays}
                onChange={(event) => setActivityDays(event.target.value)}
                disabled={pending}
              />
              <span>days</span>
            </div>
            <span className="field-note">Choose from 1 to 365 days</span>
          </div>
        </div>
        <div className="retention-explanation">
          <Clock3 size={17} aria-hidden="true" />
          <div>
            <strong>Expiry stays predictable.</strong>
            <p>
              New reviews use your content default. Changing it won’t extend or shorten reviews already saved.
            </p>
          </div>
        </div>
        {error && <InlineNotice error>{error}</InlineNotice>}
        {notice && <InlineNotice>{notice}</InlineNotice>}
        <div className="settings-save-row">
          <button className="quiet-button" type="button" onClick={onReload} disabled={pending}>
            <RotateCcw size={14} aria-hidden="true" /> Reload defaults
          </button>
          <button type="submit" disabled={pending || !changed}>
            {pending ? 'Saving…' : 'Save defaults'}
          </button>
        </div>
      </form>
      <CleanupHealthPanel key={settings.id} workspaceId={settings.id} />
    </div>
  )
}
