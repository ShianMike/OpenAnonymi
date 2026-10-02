import * as Dialog from '@radix-ui/react-dialog'
import { Keyboard, CircleHelp } from 'lucide-react'
import type { ReviewController } from '../review/useReviewController'
import { sameVersion } from '../review/reviewState'
import { ChoiceSwitch, DialogFrame } from '../ui/WorkspaceControls'
import { GlassSelect } from '../ui/GlassSelect'
import { shortcutGuide } from './shortcuts'
import { useKeyboardReview } from './useKeyboardReview'
import './keyboard-review.css'

export function KeyboardReview({ review, userId, compact = false }: { review: ReviewController; userId: string; compact?: boolean }) {
  const mode = useKeyboardReview(review, userId)
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const finding = review.activeFindings.find((item) => item.finding_id === mode.keep?.finding)
  const currentKeep = mode.keep && saved && sameVersion(mode.keep.version, saved.version)
  return <section className={`keyboard-review${compact ? ' keyboard-review--compact' : ''}`} aria-label="Keyboard review controls">
    <span className="keyboard-review-icon"><Keyboard size={20} strokeWidth={1.5} aria-hidden="true" /></span>
    <ChoiceSwitch label="Keyboard review mode" checked={mode.enabled} onChange={mode.toggle}
      description={mode.enabled ? mode.blocked ? 'Paused while saving or editing.' : compact ? 'N / P · L · R · K · U' : 'N / P to move · L label · R redact · K keep · U undo' : compact ? undefined : 'Turn on shortcuts to review without switching to your mouse.'} />
    <Dialog.Root open={mode.help} onOpenChange={mode.setHelp}>
      <Dialog.Trigger asChild><button type="button" className="keyboard-guide-button" aria-label="Shortcut guide" title="Shortcut guide"><CircleHelp size={16} aria-hidden="true" /><span>Shortcut guide</span></button></Dialog.Trigger>
      <DialogFrame title="A little faster. Still your call." description="Keyboard shortcuts apply to one selected occurrence in the visible finding list. Turn on keyboard review mode to use them.">
        <dl className="keyboard-shortcut-list">{shortcutGuide.map(([key, name, note]) => <div key={key}>
          <dt><kbd>{key}</kbd><strong>{name}</strong></dt><dd>{note}</dd>
        </div>)}</dl>
        <p className="field-note">Shortcuts pause in text fields, menus, dialogs, during saving, and when the review needs a reload. They never confirm the review or export it.</p>
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
  </section>
}
