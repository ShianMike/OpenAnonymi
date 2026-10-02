import { ArrowRight, Check, FileText, ShieldCheck } from 'lucide-react'
import type { SessionView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
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
      <PageHeader
        title="New review"
        titleId="new-review-title"
        description="A little care before you share. Start with the text you want to review."
      />
      <ol className="intake-steps" aria-label="Review workflow">
        <li aria-current="step">
          <span>01</span> Add your content
        </li>
        <li>
          <ArrowRight size={14} aria-hidden="true" />
          <span>02</span> Review findings
        </li>
        <li>
          <ArrowRight size={14} aria-hidden="true" />
          <span>03</span> Share with care
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
      <form className="review-intake-layout" onSubmit={intake.save}>
        <IntakeSource intake={intake} />
        <aside className="review-intake-sidebar" aria-label="Review setup">
          <IntakeOptions intake={intake} />
          <div className="intake-submit-panel">
            {intake.error && <InlineNotice error>{intake.error}</InlineNotice>}
            <button className="intake-save" type="submit" disabled={!intake.readyToSave}>
              {intake.submitting ? <><LoadingMark small /> Saving draft…</> : intake.pending ? 'Preparing review…' : <>Save draft <ArrowRight size={17} aria-hidden="true" /></>}
            </button>
            <p>
              <ShieldCheck size={14} aria-hidden="true" /> You control who can review your document.
            </p>
          </div>
        </aside>
      </form>
      <AutosaveStatus recovery={intake.recovery} dirty={intake.intakeDirty} />
      <div className="intake-reassurance">
        <FileText size={16} aria-hidden="true" />
        <span>Your original stays intact.</span>
        <Check size={14} aria-hidden="true" />
        <span>You decide what changes.</span>
      </div>
    </section>
  )
}
