import { useId, useState } from 'react'
import { GlassSelect } from '../ui/GlassSelect'
import type { ReviewFinding } from './textSegments'
import type { ReviewController } from './useReviewController'
import { choiceKey, styleDisclosure, styleLabel, useStyleControls, type ReviewAction } from './useStyleControls'
import './style-controls.css'

export function StyleControls({ finding, review }: { finding: ReviewFinding; review: ReviewController }) {
  if (review.state.kind !== 'ready') return null
  return <Choices key={`${finding.finding_id}:${review.state.saved.version.decision_version}`} finding={finding} review={review} source={review.state.saved} />
}

function Choices({ finding, review, source }: { finding: ReviewFinding; review: ReviewController; source: Extract<ReviewController['state'], {kind: 'ready'}>['saved'] }) {
  const id = useId()
  const [attempted, setAttempted] = useState(false)
  const { groupTriggerRef, groupConfirmRef, confirmGroupDecision, cancelGroupDecision } = review
  const mode = useStyleControls(source, finding, review.preview)
  const blocked = review.actionPending || review.dirty || review.settingsDirty || review.conflict
  const disclosure = styleDisclosure(mode.choice)
  const linked = finding.group_id ? review.groupMembers.get(finding.group_id) ?? [] : []
  const fallback = review.preview?.stand_in_fallback_ids?.includes(finding.finding_id)
  return <section className="style-controls" aria-label="Replacement style">
    <label className="field-label" htmlFor={`${id}-action`}>Decision action</label>
    <GlassSelect id={`${id}-action`} value={mode.action} disabled={blocked} onValueChange={(value) => mode.changeAction(value as ReviewAction)}>
      <option value="label">Label</option><option value="redact">Redact</option><option value="keep">Keep</option>
    </GlassSelect>
    <label className="field-label" htmlFor={`${id}-style`}>Replacement style</label>
    <GlassSelect id={`${id}-style`} value={mode.selected} disabled={blocked} onValueChange={mode.setSelected}>
      {mode.choices.map((choice) => <option value={choiceKey(choice)} key={choiceKey(choice)}>{styleLabel(choice, mode.action)}</option>)}
    </GlassSelect>
    {disclosure && <p className="field-note">{disclosure}</p>}
    {finding.category === 'phone' && !review.preview?.style_capabilities?.[finding.finding_id]?.label?.some((choice) => choice.style === 'stand_in') &&
      <p className="field-note">A verified fictional phone range is unavailable for this number. Choose a partial mask instead.</p>}
    {finding.category === 'date' && !finding.date_format && <p className="field-note">This date could not be parsed. A category label or [REDACTED] is available.</p>}
    {fallback && <p role="status" className="field-note">A unique fictional replacement could not be found. This occurrence uses its category label.</p>}
    <button type="button" className="button-primary" disabled={blocked}
      onClick={() => { setAttempted(true); void review.changeReview('decision', finding.finding_id, { action: mode.action, choice: mode.choice }) }}>Apply style to this occurrence</button>
    {linked.length > 1 && <button type="button" disabled={blocked} onClick={(event) => {
      if (review.state.kind !== 'ready') return
      groupTriggerRef.current = event.currentTarget
      review.setGroupConfirmation({ findingId: finding.finding_id, action: mode.action, choice: mode.choice,
        affectedIds: linked.map((item) => item.finding_id), spans: linked.map((item) => item.span), version: review.state.saved.version })
    }}>Review style for all linked</button>}
    {review.groupConfirmation?.findingId === finding.finding_id && review.groupConfirmation.choice && <div className="style-group-confirmation" role="group" aria-label="Confirm linked style">
      <p>Apply {styleLabel(review.groupConfirmation.choice, review.groupConfirmation.action)} to {review.groupConfirmation.affectedIds.length} occurrences at {review.groupConfirmation.spans.map((span) => `${span.start + 1}–${span.end}`).join(', ')}?</p>
      {linked.map((item) => <p key={item.finding_id}><strong>{item.span.start + 1}–{item.span.end}</strong> · {review.codePoints.slice(item.span.start, item.span.end).join('')}</p>)}
      <button type="button" ref={groupConfirmRef} disabled={blocked} onClick={() => { setAttempted(true); confirmGroupDecision() }}>Apply style to all linked</button>
      <button type="button" disabled={blocked} onClick={cancelGroupDecision}>Cancel</button>
    </div>}
    {attempted && review.error && <p role="alert" className="finding-popover-error">{review.error}</p>}
  </section>
}
