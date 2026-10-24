import { Link } from 'react-router-dom'
import { ChevronLeft, ArrowRight, Fingerprint, LockKeyhole } from 'lucide-react'
import type { SessionView } from '../api/client'
import { workspaceHref } from '../shell/navigation'
import { StudioSelect } from './studio/StudioControls'
import { StudioTheme } from './studio/StudioTheme'
import { UnsavedNavigationPrompt } from '../ui/UnsavedNavigationPrompt'
import { IntakeSource } from './intake/IntakeSource'
import { IntakeOptions } from './intake/IntakeOptions'
import { useIntake } from './intake/useIntake'
import { AutosaveStatus } from '../recovery/AutosaveStatus'
import { QuickGuideButton } from '../onboarding/QuickGuide'
import './intake/intake.css'

export function NewReviewPage({ session, onUnsavedChange }: { session: SessionView; onUnsavedChange?: (dirty: boolean) => void }) {
  const intake = useIntake(session)
  return <section className="studio studio-intake" aria-labelledby="new-review-title">
    <header className="studio-topbar"><Link to={workspaceHref('/documents', intake.workspaceId)} className="studio-back" aria-label="Back to documents"><ChevronLeft size={18} aria-hidden="true" /><span>Documents</span></Link><Fingerprint size={24} className="studio-brand" aria-label="OpenAnonymi" />
      <div className="studio-title"><h1 id="new-review-title">New privacy review</h1><span>{session.memberships.find(item => item.workspace_id === intake.workspaceId)?.workspace_name ?? 'Your workspace'}<span className="studio-title-separator">/</span>Draft</span></div>
      {session.memberships.length > 1 && <div className="studio-workspace-picker"><label className="sr-only" htmlFor="intake-workspace">Workspace</label><StudioSelect id="intake-workspace" value={intake.workspaceId} disabled={intake.pending} onValueChange={value => { intake.setDefaults({ kind: 'loading' }); intake.setWorkspaceId(value) }}>{session.memberships.map((item, index) => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || `Workspace ${index + 1}`}</option>)}</StudioSelect></div>}
      <div className="studio-header-actions"><QuickGuideButton /><StudioTheme /></div>
    </header>
    <UnsavedNavigationPrompt when={intake.intakeDirty && !intake.recovery.protected} focusBackId={intake.mode === 'paste' ? 'source-text' : 'source-file'} allowNavigationRef={intake.allowNavigationRef} onDirtyChange={onUnsavedChange} onSaveAndLeave={intake.recovery.flush} onDiscardAndLeave={intake.recovery.clear} />
    <form className="studio-intake-form" onSubmit={intake.save}>
      <div className="studio-intake-source"><div className="studio-intake-intro"><h2>Prepare your document</h2><p>Upload a file or paste your text. Choose what to check, then review each suggestion.</p></div><IntakeSource intake={intake} /></div>
      <aside className="studio-intake-settings"><div className="studio-intake-settings-scroll"><div className="studio-intake-settings-heading"><h2>Review settings</h2></div><IntakeOptions intake={intake} /></div>
        <footer className="studio-intake-submit">{intake.error && <p className="studio-error" role="alert">{intake.error}</p>}
          <button className="studio-primary" type="submit" name="action" value="scan" disabled={!intake.readyToSave} aria-describedby="intake-save-help">{intake.submitting ? intake.findingSuggestions ? 'Finding suggestions…' : 'Saving draft…' : intake.pending ? 'Preparing…' : 'Start review'}<ArrowRight size={16} /></button>
          <button type="submit" name="action" value="save" disabled={!intake.readyToSave} aria-label="Save draft without scanning">Save as draft</button>
          <p id="intake-save-help">{intake.fileLoading ? 'Extracting text from your file…' : intake.fileError ? 'Resolve the file error to continue.' : intake.overLimit ? 'Shorten the text to continue.' : !intake.characters ? 'Add your content to get started.' : 'Nothing is replaced until you choose.'}</p>
        </footer>
      </aside>
    </form>
    <footer className="studio-statusbar"><span><LockKeyhole size={12} />Your original stays intact</span><AutosaveStatus recovery={intake.recovery} dirty={intake.intakeDirty} /></footer>
  </section>
}
