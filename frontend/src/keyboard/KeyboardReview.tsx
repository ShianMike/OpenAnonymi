import * as Dialog from '@radix-ui/react-dialog'
import { Keyboard, ChevronDown } from 'lucide-react'
import type { ReviewController } from '../review/useReviewController'
import { sameVersion } from '../review/reviewState'
import { ChoiceSwitch, DialogFrame } from '../ui/WorkspaceControls'
import { GlassSelect } from '../ui/GlassSelect'
import { shortcutGuide } from './shortcuts'
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
    <ChoiceSwitch label="Keyboard shortcuts" checked={mode.enabled} onChange={mode.toggle}
      description={mode.enabled ? mode.blocked ? 'Paused while saving or editing.' : 'On · N / P to move' : 'Off · Turn on to use keys'} />
    <Dialog.Root open={mode.help} onOpenChange={mode.setHelp}>
      <Dialog.Trigger asChild><button type="button" className="keyboard-guide-button" aria-label="Shortcut guide" title="Shortcut guide"><Keyboard size={17} aria-hidden="true" /><span>Guide</span></button></Dialog.Trigger>
      <DialogFrame title="Keyboard shortcuts" description="Turn on shortcuts to move through details and choose what to share.">
        <div className="keyboard-guide-body">
          <h3>Move and review</h3>
          <dl className="keyboard-shortcut-list">{shortcutGuide.slice(0, 6).map(([key, name, note]) => <div key={key}>
            <dt><kbd>{key}</kbd><strong>{name}</strong></dt><dd>{note}</dd>
          </div>)}</dl>
          <details className="keyboard-shortcut-more">
            <summary>More ways to hide or replace details <ChevronDown size={16} aria-hidden="true" /></summary>
            <p>These options work only when the selected detail supports them.</p>
            <dl className="keyboard-shortcut-list">{shortcutGuide.slice(6, -1).map(([key, name, note]) => <div key={key}>
              <dt><kbd>{key}</kbd><strong>{name}</strong></dt><dd>{note}</dd>
            </div>)}</dl>
          </details>
        </div>
        <div className="keyboard-guide-footer">
          <span><kbd>?</kbd> Open guide <kbd>Esc</kbd> Close</span>
          <p>Shortcuts pause while you type, save, or open a menu or dialog. Use the review buttons to confirm and share.</p>
        </div>
      </DialogFrame>
    </Dialog.Root>
    {!mode.savedPreference && <p className="field-note">Enabled for this visit. Your browser did not save this preference.</p>}
    <Dialog.Root open={Boolean(mode.keep)} onOpenChange={(open) => { if (!open && !mode.pending) mode.setKeep(null) }}>
      <DialogFrame title="Keep this detail?" description="Choose why this occurrence should remain in the reviewed output." busy={mode.pending} onCloseAutoFocus={mode.restoreKeepFocus}>
        {finding && <p className="keyboard-keep-value">{review.codePoints.slice(finding.span.start, finding.span.end).join('')}</p>}
        <label className="field-label" htmlFor="keyboard-keep-reason">Reason for keeping</label>
        <GlassSelect id="keyboard-keep-reason" value={mode.reason} disabled={mode.pending} onValueChange={(value) => mode.setReason(value as typeof mode.reason)}>
          <option value="">Choose a reason</option>
          <option value="false_match" data-description="This finding does not identify sensitive information.">False match</option>
          <option value="intended_disclosure" data-description="You intentionally want this detail to remain.">Intended disclosure</option>
        </GlassSelect>
        {!currentKeep && <p role="alert">The review version changed. Close this dialog and review the detail again.</p>}
        {review.error && <p role="alert">{review.error}</p>}
        <div className="keyboard-keep-actions">
          <Dialog.Close asChild><button type="button" disabled={mode.pending}>Cancel</button></Dialog.Close>
          <button type="button" className="button-primary" disabled={!finding || !currentKeep || !mode.reason || mode.blocked || mode.pending}
            onClick={() => { if (finding && mode.reason) void mode.perform('keep', finding.finding_id, mode.reason) }}>Keep with this reason</button>
        </div>
      </DialogFrame>
    </Dialog.Root>
    <Dialog.Root open={Boolean(mode.generalize)} onOpenChange={(open) => { if (!open && !mode.pending) mode.setGeneralize(null) }}>
      <DialogFrame title="Generalize this date" description="Choose which parts stay visible." busy={mode.pending}>
        {dateFinding && <p className="keyboard-keep-value">{review.codePoints.slice(dateFinding.span.start, dateFinding.span.end).join('')}</p>}
        {!currentGeneralize && <p role="alert">The review version changed. Close this dialog and review the date again.</p>}
        {dateFinding && availableChoices(review.preview, dateFinding, 'redact').filter((choice) => choice.style === 'generalize').map((choice) =>
          <div key={choiceKey(choice)}><button type="button" disabled={!currentGeneralize || mode.blocked || mode.pending}
            onClick={() => void mode.perform('redact', dateFinding.finding_id, undefined, choice)}>{styleLabel(choice, 'redact')}</button><p className="field-note">{styleDisclosure(choice)}</p></div>)}
        {review.error && <p role="alert">{review.error}</p>}
        <Dialog.Close asChild><button type="button" disabled={mode.pending}>Cancel</button></Dialog.Close>
      </DialogFrame>
    </Dialog.Root>
  </section>
}
