import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { Keyboard, CircleHelp } from 'lucide-react'
import type { ReviewController } from '../review/useReviewController'
import { sameVersion } from '../review/reviewState'
import { StudioDialog, StudioSelect } from '../review/studio/StudioControls'
import { ShortcutGuide } from './ShortcutGuide'
import { useKeyboardReview } from './useKeyboardReview'
import './keyboard-review.css'
import { availableChoices, styleLabel, styleDisclosure, choiceKey } from '../review/useStyleControls'

export function KeyboardReview({ review, userId, compact = false }: { review: ReviewController; userId: string; compact?: boolean }) {
  const mode = useKeyboardReview(review, userId)
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const finding = review.activeFindings.find((item) => item.finding_id === mode.keep?.finding)
  const currentKeep = mode.keep && saved && sameVersion(mode.keep.version, saved.version)
  const dateFinding = review.activeFindings.find((item) => item.finding_id === mode.generalize?.finding)
  const currentGeneralize = mode.generalize && saved && sameVersion(mode.generalize.version, saved.version)
  return <section className={`keyboard-review${compact ? ' keyboard-review--compact' : ''}`} aria-label="Keyboard review controls">
    <span className="keyboard-review-icon"><Keyboard size={20} strokeWidth={1.5} aria-hidden="true" /></span>
    {compact ? <Popover.Root>
      <Popover.Trigger asChild><button type="button" className="keyboard-mode-button" aria-label="Keyboard shortcut options">
        <Keyboard size={16} aria-hidden="true" /> Shortcuts
      </button></Popover.Trigger>
      <Popover.Portal><Popover.Content className="studio keyboard-mode-popover" align="end" sideOffset={8} collisionPadding={12}>
        <label className="studio-shortcut-switch"><span><strong>Keyboard shortcuts</strong><small>{mode.enabled ? mode.blocked ? 'Paused while saving or editing.' : 'N / P to move between findings' : 'Use keys to review faster'}</small></span><input type="checkbox" checked={mode.enabled} onChange={event => mode.toggle(event.target.checked)} /></label>
      </Popover.Content></Popover.Portal>
    </Popover.Root> : <label className="studio-shortcut-switch">Keyboard shortcuts<input type="checkbox" checked={mode.enabled} onChange={event => mode.toggle(event.target.checked)} /></label>}
    <Dialog.Root open={mode.help} onOpenChange={mode.setHelp}>
      <Dialog.Trigger asChild><button type="button" className="keyboard-guide-button" aria-label="Shortcut guide" title="Shortcut guide"><CircleHelp size={17} aria-hidden="true" /><span>Guide</span></button></Dialog.Trigger>
      <StudioDialog className="studio-shortcut-guide" title="Keyboard shortcuts" description="Find a key or an action. Shortcuts never confirm or share a review."
        onOpenAutoFocus={event => {
          if (event.target instanceof HTMLElement) {
            event.preventDefault()
            event.target.querySelector<HTMLInputElement>('.shortcut-search input')?.focus()
          }
        }}>
        <ShortcutGuide />
        <div className="keyboard-guide-footer">
          <label className="studio-shortcut-switch"><span><strong>Enable review shortcuts</strong><small>{mode.enabled ? 'Ready when you return to the document.' : 'Turn on keys for faster review.'}</small></span><input type="checkbox" checked={mode.enabled} onChange={event => mode.toggle(event.target.checked)} /></label>
          <p>Keys pause while you type, save, or open a dialog. <kbd>Esc</kbd> closes this guide.</p>
        </div>
      </StudioDialog>
    </Dialog.Root>
    {!mode.savedPreference && <p className="field-note">Enabled for this visit. Your browser did not save this preference.</p>}
    <Dialog.Root open={Boolean(mode.keep)} onOpenChange={(open) => { if (!open && !mode.pending) mode.setKeep(null) }}>
      <StudioDialog className="studio-keyboard-dialog" title="Keep this detail?" description="Choose why this occurrence should remain in the reviewed output." busy={mode.pending} onCloseAutoFocus={mode.restoreKeepFocus}>
        {finding && <p className="keyboard-keep-value">{review.codePoints.slice(finding.span.start, finding.span.end).join('')}</p>}
        <label className="field-label" htmlFor="keyboard-keep-reason">Reason for keeping</label>
        <StudioSelect id="keyboard-keep-reason" value={mode.reason} disabled={mode.pending} onValueChange={(value) => mode.setReason(value as typeof mode.reason)}>
          <option value="">Choose a reason</option>
          <option value="false_match" data-description="This finding does not identify sensitive information.">False match</option>
          <option value="intended_disclosure" data-description="You intentionally want this detail to remain.">Intended disclosure</option>
        </StudioSelect>
        {!currentKeep && <p role="alert">The review version changed. Close this dialog and review the detail again.</p>}
        {review.error && <p role="alert">{review.error}</p>}
        <div className="keyboard-keep-actions">
          <Dialog.Close asChild><button type="button" disabled={mode.pending}>Cancel</button></Dialog.Close>
          <button type="button" className="button-primary" disabled={!finding || !currentKeep || !mode.reason || mode.blocked || mode.pending}
            onClick={() => { if (finding && mode.reason) void mode.perform('keep', finding.finding_id, mode.reason) }}>Keep with this reason</button>
        </div>
      </StudioDialog>
    </Dialog.Root>
    <Dialog.Root open={Boolean(mode.generalize)} onOpenChange={(open) => { if (!open && !mode.pending) mode.setGeneralize(null) }}>
      <StudioDialog className="studio-keyboard-dialog" title="Generalize this date" description="Choose which parts stay visible." busy={mode.pending}>
        {dateFinding && <p className="keyboard-keep-value">{review.codePoints.slice(dateFinding.span.start, dateFinding.span.end).join('')}</p>}
        {!currentGeneralize && <p role="alert">The review version changed. Close this dialog and review the date again.</p>}
        {dateFinding && availableChoices(review.preview, dateFinding, 'redact').filter((choice) => choice.style === 'generalize').map((choice) =>
          <div key={choiceKey(choice)}><button type="button" disabled={!currentGeneralize || mode.blocked || mode.pending}
            onClick={() => void mode.perform('redact', dateFinding.finding_id, undefined, choice)}>{styleLabel(choice, 'redact')}</button><p className="field-note">{styleDisclosure(choice)}</p></div>)}
        {review.error && <p role="alert">{review.error}</p>}
        <Dialog.Close asChild><button type="button" disabled={mode.pending}>Cancel</button></Dialog.Close>
      </StudioDialog>
    </Dialog.Root>
  </section>
}
