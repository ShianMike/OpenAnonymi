import { cloneElement, useId, useState, type ButtonHTMLAttributes, type ReactElement } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { Check, Eye, ScanLine, Tag, X } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import type { ReviewController } from './useReviewController'
import type { ReviewFinding } from './textSegments'
import './finding-popover.css'
import { CategoryBadge } from '../rules/CategoryBadge'
import { StyleControls } from './StyleControls'

const actions = [
  { value: 'label', title: 'Label', description: 'Use a consistent placeholder', icon: Tag },
  {
    value: 'redact',
    title: 'Redact',
    description: 'Hide this detail from the output',
    icon: ScanLine,
  },
  { value: 'keep', title: 'Keep', description: 'Leave this detail in the output', icon: Eye },
] as const

export function FindingPopover({
  finding,
  review,
  children,
  getReview,
}: {
  finding: ReviewFinding
  review: ReviewController
  children: ReactElement<ButtonHTMLAttributes<HTMLButtonElement>>
  getReview?: () => ReviewController
}) {
  const [open, setOpen] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const titleId = useId()
  const reasonId = useId()
  const saving = review.pendingDecisionIds.includes(finding.finding_id)
  const blocked = review.decisionBlocked || saving || review.dirty || review.settingsDirty || review.conflict
  const value = open ? review.codePoints.slice(finding.span.start, finding.span.end).join('') : ''
  const linkedCount = finding.group_id
    ? (review.groupMembers.get(finding.group_id)?.length ?? 1)
    : 1
  function changeOpen(next: boolean) {
    setOpen(next)
    setAttempted(false)
    if (next) {
      const current = getReview?.() ?? review
      current.setSelectedFindingId(finding.finding_id)
      current.setKeepReason(
        finding.keep_reason === 'intended_disclosure' ? 'intended_disclosure' : 'false_match',
      )
    }
  }
  // Keep the selected trigger mounted for Radix focus restoration. Other marks
  // remain native buttons instead of mounting hundreds of closed popover trees.
  if (!open && review.selectedFindingId !== finding.finding_id) {
    return cloneElement(children, { 'aria-haspopup': 'dialog', 'aria-expanded': false, onClick: event => {
      children.props.onClick?.(event)
      const current = getReview?.() ?? review
      if (!event.defaultPrevented && !current.dirty && !current.settingsDirty) changeOpen(true)
    } })
  }
  return (
    <Popover.Root
      open={open && !review.dirty && !review.settingsDirty}
      onOpenChange={changeOpen}
    >
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      {open && <Popover.Portal>
        <Popover.Content
          className="finding-popover"
          side="bottom"
          align="start"
          sideOffset={10}
          collisionPadding={16}
          hideWhenDetached
          aria-labelledby={titleId}
        >
          <div className="finding-popover-heading">
            <CategoryBadge category={finding.category} />
            <Popover.Close className="quiet-icon" aria-label="Close finding options">
              <X size={17} aria-hidden="true" />
            </Popover.Close>
          </div>
          <h3 id={titleId}>{value}</h3>
          <p className="finding-popover-reason">
            {finding.reason || 'You marked this detail for review.'}
          </p>
          <div className="finding-popover-actions" role="group" aria-label="Choose a decision">
            {actions.map(({ value: action, title, description, icon: Icon }) => (
              <button
                type="button"
                key={action}
                aria-pressed={finding.action === action}
                disabled={blocked}
                onClick={async () => {
                  setAttempted(true)
                  const saved = await review.changeReview('decision', finding.finding_id, {
                    action,
                  })
                  if (saved) setOpen(false)
                }}
              >
                <span className="finding-popover-action-icon">
                  <Icon size={18} strokeWidth={1.6} aria-hidden="true" />
                </span>
                <span>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </span>
                {finding.action === action && <Check size={16} aria-hidden="true" />}
              </button>
            ))}
          </div>
          <label className="field-label" htmlFor={reasonId}>
            Reason if kept
          </label>
          <GlassSelect
            id={reasonId}
            value={review.keepReason}
            disabled={blocked}
            onValueChange={(value) => review.setKeepReason(value as typeof review.keepReason)}
          >
            <option value="false_match">False match</option>
            <option value="intended_disclosure">Intended disclosure</option>
          </GlassSelect>
          {open && <StyleControls finding={finding} review={review} />}
          {(review.findingPending || saving) && (
            <p role="status" className="finding-popover-feedback">
              Saving decision…
            </p>
          )}
          {attempted && !review.findingPending && !saving && review.error && (
            <p role="alert" className="finding-popover-error">
              {review.error}
            </p>
          )}
          {review.conflict && (
            <p role="alert" className="finding-popover-error">
              Reload the saved review before changing this detail.
            </p>
          )}
          <p className="finding-popover-footnote">
            {linkedCount > 1
              ? `This occurrence only · ${linkedCount} linked details`
              : 'Your original text stays intact.'}
          </p>
          <Popover.Arrow className="finding-popover-arrow" width={12} height={6} />
        </Popover.Content>
      </Popover.Portal>}
    </Popover.Root>
  )
}
