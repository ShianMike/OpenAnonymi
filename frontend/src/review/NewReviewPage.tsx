import { ArrowRight, ShieldCheck } from 'lucide-react'
import type { SessionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { InlineNotice } from '../ui/WorkspaceControls'
import { UnsavedNavigationPrompt } from '../ui/UnsavedNavigationPrompt'
import { IntakeSource } from './intake/IntakeSource'
import { IntakeOptions } from './intake/IntakeOptions'
import { useIntake } from './intake/useIntake'
import { AutosaveStatus } from '../recovery/AutosaveStatus'
import { LoadingMark } from '../loading/LoadingMark'
import './intake/intake.css'

export function NewReviewPage({
  session,
  onUnsavedChange,
}: {
  session: SessionView
  onUnsavedChange?: (dirty: boolean) => void
}) {
  const intake = useIntake(session)
  return (
    <section className="new-review-page" aria-labelledby="new-review-title">
      <header className="intake-heading">
        <div>
          <h1 id="new-review-title">New review</h1>
          <p>Paste text or upload a file. We’ll help you spot details you may want to keep private.</p>
        </div>
        <div className="intake-heading-tools">
          {session.memberships.length > 1 && (
            <div className="workspace-picker">
              <label htmlFor="intake-workspace">Workspace</label>
              <GlassSelect
                id="intake-workspace"
                value={intake.workspaceId}
                disabled={intake.pending}
                onValueChange={(value) => {
                  intake.setDefaults({ kind: 'loading' })
                  intake.setWorkspaceId(value)
                }}
              >
                {session.memberships.map((item, index) => (
                  <option key={item.workspace_id} value={item.workspace_id}>
                    {item.workspace_name || `Workspace ${index + 1}`}
                  </option>
                ))}
              </GlassSelect>
            </div>
          )}
        </div>
      </header>
      <ol className="intake-steps" aria-label="Review workflow">
        <li aria-current="step">
          <span>01</span> Add text
        </li>
        <li>
          <ArrowRight size={14} aria-hidden="true" />
          <span>02</span> Check details
        </li>
        <li>
          <ArrowRight size={14} aria-hidden="true" />
          <span>03</span> Share when ready
        </li>
      </ol>
      <UnsavedNavigationPrompt
        when={intake.intakeDirty && !intake.recovery.protected}
        focusBackId={intake.mode === 'paste' ? 'source-text' : 'source-file'}
        allowNavigationRef={intake.allowNavigationRef}
        onDirtyChange={onUnsavedChange}
        onSaveAndLeave={intake.recovery.flush}
        onDiscardAndLeave={intake.recovery.clear}
      />
      <form className="review-intake-layout" onSubmit={intake.save}>
        <div className="intake-content-column workspace-panel">
          <IntakeSource intake={intake} />
          <div className="intake-submit-panel">
            <div className="intake-submit-row">
              {intake.error && <InlineNotice error>{intake.error}</InlineNotice>}
              <div className="intake-submit-copy">
                <strong>Next: check for private details</strong>
                <p id="intake-save-help">{intake.fileLoading ? 'Reading your file. You can check the text next.'
                  : intake.characters === 0 ? 'Add some text or choose a file to get started.'
                  : 'Save your text, then choose which details to change.'}</p>
              </div>
              <button className="intake-save" type="submit" disabled={!intake.readyToSave} aria-describedby="intake-save-help">
                {intake.submitting ? <><LoadingMark small /> Saving draft…</> : intake.pending ? 'Preparing review…' : <>Save draft <ArrowRight size={17} aria-hidden="true" /></>}
              </button>
            </div>
            <AutosaveStatus recovery={intake.recovery} dirty={intake.intakeDirty} />
          </div>
        </div>
        <aside className="review-intake-sidebar" aria-label="Review options">
          <IntakeOptions intake={intake} />
          <p className="intake-reassurance"><ShieldCheck size={17} aria-hidden="true" /> Your original stays intact. You decide what changes before sharing.</p>
        </aside>
      </form>
    </section>
  )
}
