import { cloneElement, useState, type ButtonHTMLAttributes, type ReactElement } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import type { ReviewFinding } from './textSegments'
import './finding-popover.css'
import '../ui/workspace-controls.css'
import { CategoryBadge } from '../rules/CategoryBadge'
import { StyleControls } from './StyleControls'

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
  const value = open ? review.codePoints.slice(finding.span.start, finding.span.end).join('') : ''
  function changeOpen(next: boolean) {
    setOpen(next)
    if (next) {
      const current = getReview?.() ?? review
      current.setSelectedFindingId(finding.finding_id)
      current.setKeepReason(
        finding.keep_reason === 'intended_disclosure' ? 'intended_disclosure' : 'false_match',
      )
    }
  }
  // Keep the selected trigger mounted for Radix focus restoration. Other marks
  // remain native buttons instead of mounting hundreds of closed dialog trees.
  if (!open && review.selectedFindingId !== finding.finding_id) {
    return cloneElement(children, { 'aria-haspopup': 'dialog', 'aria-expanded': false, onClick: event => {
      children.props.onClick?.(event)
      const current = getReview?.() ?? review
      if (!event.defaultPrevented && !current.dirty && !current.settingsDirty) changeOpen(true)
    } })
  }
  return (
    <Dialog.Root
      open={open && !review.dirty && !review.settingsDirty}
      onOpenChange={changeOpen}
    >
      <Dialog.Trigger asChild>{children}</Dialog.Trigger>
      {open && <Dialog.Portal>
        <Dialog.Overlay className="workspace-dialog-overlay" />
        <Dialog.Content
          className="finding-popover"
        >
          <header className="finding-popover-header">
            <div className="finding-popover-heading">
              <CategoryBadge category={finding.category} />
              <Dialog.Close className="quiet-icon" aria-label="Close finding options">
                <X size={17} aria-hidden="true" />
              </Dialog.Close>
            </div>
            <Dialog.Title asChild><h3>{value}</h3></Dialog.Title>
            <Dialog.Description className="finding-popover-reason">Choose how this detail appears in the shared text.</Dialog.Description>
          </header>
          <StyleControls finding={finding} review={review} onApplied={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>}
    </Dialog.Root>
  )
}
