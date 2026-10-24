import { useId, useRef, useState } from 'react'
import { updateWorkspaceSettings, type WorkspaceSettingsView } from '../../api/client'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { CleanupHealthPanel } from './CleanupHealthPanel'
import { SettingsConfirmation } from './SettingsConfirmation'
import { validRetention } from './settingsNavigation'

export function RetentionPanel({ settings, csrfToken, onSaved, onReload, onRequestFailed }: {
  settings: WorkspaceSettingsView; csrfToken: string; onSaved: (value: WorkspaceSettingsView) => void
  onReload: () => void; onRequestFailed: (cause: unknown) => void
}) {
  const id = useId()
  const [contentDays, setContentDays] = useState(String(settings.content_retention_days))
  const [activityDays, setActivityDays] = useState(String(settings.activity_retention_days))
  const [pending, setPending] = useState(false)
  const [review, setReview] = useState<'save' | 'reload' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [conflict, setConflict] = useState(false)
  const saveButton = useRef<HTMLButtonElement>(null)
  const changed = Number(contentDays) !== settings.content_retention_days || Number(activityDays) !== settings.activity_retention_days
  const valid = validRetention(contentDays, activityDays)
  function reset() { setContentDays(String(settings.content_retention_days)); setActivityDays(String(settings.activity_retention_days)); if (!conflict) setError(''); setNotice('') }
  async function save() {
    if (pending || !valid || !changed || conflict) return
    setPending(true); setError(''); setNotice('')
    try {
      const updated = await updateWorkspaceSettings(settings.id, settings.settings_version, Number(contentDays), Number(activityDays), csrfToken)
      onSaved(updated); setContentDays(String(updated.content_retention_days)); setActivityDays(String(updated.activity_retention_days)); setReview(null)
      setNotice('Retention settings saved. Existing document expiry dates are unchanged.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Retention settings could not be saved.'); setConflict(true); setReview(null); onRequestFailed(cause) }
    finally { setPending(false) }
  }
  return <>
    <form id={id} className="settings-retention-form" onSubmit={event => { event.preventDefault(); if (valid && changed) setReview('save') }}>
      <section className="settings-section" aria-labelledby="settings-content-days"><header className="settings-section-heading"><h3 id="settings-content-days">Review content</h3><p>The default lifetime for newly created reviews.</p></header>
        <div className="settings-value-row"><div><label htmlFor={`${id}-content`}>Keep document content for</label><p id={`${id}-content-help`}>Choose from 1 to 30 days. Existing review expiry dates stay the same.</p></div><div className="settings-number"><input id={`${id}-content`} aria-label="Document content days" aria-describedby={`${id}-content-help`} type="number" min={1} max={30} step={1} required value={contentDays} onChange={event => { setContentDays(event.target.value); setNotice('') }} disabled={pending} /><span>days</span></div></div>
      </section>
      <section className="settings-section" aria-labelledby="settings-activity-days"><header className="settings-section-heading"><h3 id="settings-activity-days">Activity records</h3><p>A record of actions without original document text.</p></header>
        <div className="settings-value-row"><div><label htmlFor={`${id}-activity`}>Keep activity records for</label><p id={`${id}-activity-help`}>Choose from 1 to 365 days. Older records become eligible for scheduled cleanup.</p></div><div className="settings-number"><input id={`${id}-activity`} aria-label="Activity days" aria-describedby={`${id}-activity-help`} type="number" min={1} max={365} step={1} required value={activityDays} onChange={event => { setActivityDays(event.target.value); setNotice('') }} disabled={pending} /><span>days</span></div></div>
      </section>
      {error && <InlineNotice error title="Check the saved retention settings" actions={<button type="button" className="settings-button" disabled={pending} onClick={() => setReview('reload')}>Reload saved retention</button>}><p>{error}</p><p>Your edits are still here. Reload the saved values before trying to save again.</p></InlineNotice>}{notice && <InlineNotice>{notice}</InlineNotice>}
      <footer className="settings-save-bar"><span>{conflict ? 'Reload required' : changed ? 'Unsaved changes' : 'Up to date'}</span><div>{changed && <button type="button" className="settings-button" disabled={pending} onClick={reset}>Reset</button>}<button ref={saveButton} type="submit" className="settings-button settings-primary" disabled={pending || !changed || !valid || conflict}>Review changes</button></div></footer>
    </form>
    <CleanupHealthPanel key={settings.id} workspaceId={settings.id} onRequestFailed={onRequestFailed} />
    <SettingsConfirmation open={review !== null} title={review === 'reload' ? 'Discard edits and reload?' : 'Save retention settings?'} description={review === 'reload' ? 'Your unsaved retention edits will be replaced with the latest saved settings.' : `These defaults apply to ${settings.name}. Existing document expiry dates stay the same.`} pending={pending} dirty={changed} confirmLabel={review === 'reload' ? 'Discard and reload' : 'Save retention settings'} danger={review === 'reload' || Number(activityDays) < settings.activity_retention_days} returnFocus={saveButton} onCancel={() => setReview(null)} onConfirm={() => { if (review === 'reload') onReload(); else void save() }}>
      {review === 'save' && <><dl className="settings-change-summary">{Number(contentDays) !== settings.content_retention_days && <div><dt>New review content</dt><dd>{settings.content_retention_days} days → <strong>{contentDays} days</strong></dd></div>}{Number(activityDays) !== settings.activity_retention_days && <div><dt>Activity records</dt><dd>{settings.activity_retention_days} days → <strong>{activityDays} days</strong></dd></div>}</dl>{Number(activityDays) < settings.activity_retention_days && <p className="settings-help">Older activity records may be permanently removed by scheduled cleanup under the shorter retention period.</p>}</>}
    </SettingsConfirmation>
  </>
}
