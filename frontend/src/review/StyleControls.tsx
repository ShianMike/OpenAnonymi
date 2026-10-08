import { useId, useState } from 'react'
import { Check, Eye, ScanLine, Tag } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import type { ReviewFinding } from './textSegments'
import type { ReviewController } from './useReviewController'
import { choiceKey, styleDisclosure, styleLabel, useStyleControls } from './useStyleControls'
import './style-controls.css'

const actions = [
  { value: 'label', title: 'Label', description: 'Use a consistent placeholder', icon: Tag },
  { value: 'redact', title: 'Redact', description: 'Hide this detail from the output', icon: ScanLine },
  { value: 'keep', title: 'Keep', description: 'Leave this detail in the output', icon: Eye },
] as const

export function StyleControls({ finding, review, onApplied }: { finding: ReviewFinding; review: ReviewController; onApplied: () => void }) {
  if (review.state.kind !== 'ready') return null
  return <Choices key={`${finding.finding_id}:${review.state.saved.version.decision_version}`} finding={finding} review={review} source={review.state.saved} onApplied={onApplied} />
}

function Choices({ finding, review, source, onApplied }: { finding: ReviewFinding; review: ReviewController; source: Extract<ReviewController['state'], {kind: 'ready'}>['saved']; onApplied: () => void }) {
  const id = useId()
  const [attempted, setAttempted] = useState(false)
  const { groupTriggerRef, groupConfirmRef, confirmGroupDecision, cancelGroupDecision } = review
  const mode = useStyleControls(source, finding, review.preview)
  const defaultReason = finding.keep_reason ?? mode.defaultKeepReason
  const [keepReason, setKeepReason] = useState<'false_match' | 'intended_disclosure' | ''>(
    defaultReason === 'false_match' || defaultReason === 'intended_disclosure' ? defaultReason : '')
  const saving = review.pendingDecisionIds.includes(finding.finding_id)
  const blocked = review.decisionBlocked || saving || review.dirty || review.settingsDirty || review.conflict
  const needsReason = mode.action === 'keep' && !keepReason
  const disclosure = styleDisclosure(mode.choice)
  const linked = finding.group_id ? review.groupMembers.get(finding.group_id) ?? [] : []
  const fallback = review.preview?.stand_in_fallback_ids?.includes(finding.finding_id)
  const confirmation = review.groupConfirmation?.findingId === finding.finding_id && review.groupConfirmation.choice
    ? review.groupConfirmation : null
  return <section className="style-controls" aria-label="Choose a decision">
    <div className="style-controls-body">
      <div className="finding-popover-actions" role="group" aria-label="How to share this detail">
        {actions.map(({ value, title, description, icon: Icon }) => <button
          type="button" key={value} aria-pressed={mode.action === value} disabled={blocked || Boolean(confirmation)}
          onClick={() => mode.changeAction(value)}>
          <span className="finding-popover-action-icon"><Icon size={18} aria-hidden="true" /></span>
          <span><strong>{title}</strong><small>{description}</small></span>
          {mode.action === value && <Check size={16} aria-hidden="true" />}
        </button>)}
      </div>
      <div className="finding-decision-options">
        {mode.action === 'keep' ? <>
          <label className="field-label" htmlFor={`${id}-reason`}>Why keep this detail?</label>
          <GlassSelect id={`${id}-reason`} value={keepReason} disabled={blocked || Boolean(confirmation)}
            aria-describedby={needsReason ? `${id}-reason-note` : undefined}
            onValueChange={(value) => setKeepReason(value as typeof keepReason)}>
            <option value="">Choose a reason</option>
            <option value="false_match">Not a private detail</option>
            <option value="intended_disclosure">I want to share this detail</option>
          </GlassSelect>
          <p className="field-note" id={`${id}-reason-note`}>{needsReason ? 'Choose why this detail can stay before saving.' : 'This detail will stay visible in the shared text.'}</p>
        </> : <>
          <label className="field-label" htmlFor={`${id}-style`}>Replacement style</label>
          <GlassSelect id={`${id}-style`} value={mode.selected} disabled={blocked || Boolean(confirmation)} onValueChange={mode.setSelected}>
            {mode.choices.map((choice) => <option value={choiceKey(choice)} key={choiceKey(choice)}>{styleLabel(choice, mode.action)}</option>)}
          </GlassSelect>
          {disclosure && <p className="field-note">{disclosure}</p>}
          {mode.action === 'label' && finding.category === 'phone' && !review.preview?.style_capabilities?.[finding.finding_id]?.label?.some((choice) => choice.style === 'stand_in') &&
            <p className="field-note">A verified fictional phone range is unavailable for this number. Choose a partial mask instead.</p>}
          {finding.category === 'date' && !finding.date_format && <p className="field-note">This date could not be parsed. A category label or [REDACTED] is available.</p>}
          {fallback && <p role="status" className="field-note">A unique fictional replacement could not be found. This occurrence uses its category label.</p>}
        </>}
      </div>
      {finding.reason && <details className="finding-decision-help">
        <summary>Why this was suggested</summary><p className="field-note">{finding.reason}</p>
      </details>}
      {linked.length > 1 && <button type="button" disabled={blocked || needsReason || Boolean(confirmation)} onClick={(event) => {
        if (review.state.kind !== 'ready') return
        groupTriggerRef.current = event.currentTarget
        review.setGroupConfirmation({ findingId: finding.finding_id, action: mode.action, choice: mode.choice,
          keepReason: mode.action === 'keep' ? keepReason || undefined : undefined,
          affectedIds: linked.map((item) => item.finding_id), spans: linked.map((item) => item.span), version: review.state.saved.version })
      }}>Review style for all linked</button>}
      {confirmation && <div className="style-group-confirmation" role="group" aria-label="Confirm linked style">
        <p>Apply {styleLabel(confirmation.choice!, confirmation.action)} to {confirmation.affectedIds.length} occurrences at {confirmation.spans.map((span) => `${span.start + 1}–${span.end}`).join(', ')}?</p>
        {linked.map((item) => <p key={item.finding_id}><strong>{item.span.start + 1}–{item.span.end}</strong> · {review.codePoints.slice(item.span.start, item.span.end).join('')}</p>)}
        <button type="button" ref={groupConfirmRef} disabled={blocked} onClick={() => { setAttempted(true); confirmGroupDecision() }}>Apply style to all linked</button>
        <button type="button" disabled={blocked} onClick={cancelGroupDecision}>Cancel</button>
      </div>}
      {attempted && review.error && <p role="alert" className="finding-popover-error">{review.error}</p>}
      {review.conflict && <p role="alert" className="finding-popover-error">Reload the saved review before changing this detail.</p>}
    </div>
    <footer className="style-controls-footer">
      <button type="button" className="button-primary" disabled={blocked || needsReason || Boolean(confirmation)}
        onClick={async () => {
          setAttempted(true)
          const accepted = await review.changeReview('decision', finding.finding_id, {
            action: mode.action, choice: mode.choice, keepReason: mode.action === 'keep' ? keepReason || undefined : undefined,
          })
          if (accepted) onApplied()
        }}>{saving ? 'Saving choice…' : 'Save choice'}</button>
      <p className="finding-popover-footnote">{linked.length > 1 ? `This occurrence only · ${linked.length} linked details` : 'Your original text stays intact.'}</p>
    </footer>
  </section>
}
