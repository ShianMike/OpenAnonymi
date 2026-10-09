import { memo, useCallback, useLayoutEffect, useMemo, useRef } from 'react'
import type { ReviewController } from './useReviewController'
import { FindingPopover } from './FindingPopover'
import { segmentText, type TextMark, type ReviewFinding, type TextSegment } from './textSegments'
import { MarkdownText } from './MarkdownText'

type MarkProps = {
  finding: ReviewFinding; segment: TextSegment; review: ReviewController
  getReview: () => ReviewController; variant: 'original' | 'preview'
  selected: boolean; disabled: boolean; fictional: boolean
}

const InlineMark = memo(function InlineMark({ finding, segment, review, getReview, variant,
  selected, disabled, fictional }: MarkProps) {
  return <FindingPopover finding={finding} review={review} getReview={getReview}>
    <button type="button" id={`mark-${variant}-${finding.finding_id}-${segment.start}`}
      className="inline-finding" data-finding-id={finding.finding_id}
      data-action={finding.action || 'pending'}
      aria-label={`${finding.category}: ${segment.text}. ${finding.action || 'Needs decision'}.${fictional ? ' Fictional stand-in.' : ''} Open options`}
      data-selected={selected || undefined} disabled={disabled}>{segment.text}</button>
  </FindingPopover>
}, (before, after) => {
  // Selected/open controls always receive the current controller. Other marks
  // are native buttons; their click reads the latest committed controller.
  if (before.selected || after.selected) return false
  return before.disabled === after.disabled && before.fictional === after.fictional &&
    before.variant === after.variant && before.getReview === after.getReview &&
    before.segment.text === after.segment.text && before.segment.start === after.segment.start &&
    before.segment.end === after.segment.end &&
    JSON.stringify(before.finding) === JSON.stringify(after.finding)
})

export function ReviewText({
  text,
  marks,
  review,
  variant,
}: {
  text: string
  marks: TextMark[]
  review: ReviewController
  variant: 'original' | 'preview'
}) {
  const segments = useMemo(() => segmentText(text, marks), [text, marks])
  const currentReview = useRef(review)
  useLayoutEffect(() => { currentReview.current = review }, [review])
  const getReview = useCallback(() => currentReview.current, [])
  return (
    <div
      className="document-text"
      tabIndex={0}
      aria-label={
        variant === 'original'
          ? 'Original text with clickable findings'
          : 'Reviewed output with clickable findings'
      }
    >
      <MarkdownText text={text} segments={segments} plain={review.state.kind === 'ready' && Boolean(review.state.saved.csv)} renderSegment={(segment) => {
        const finding = segment.findings[0]
        if (!finding) return segment.text
        return (
          <InlineMark
            key={`${finding.finding_id}-${segment.start}`}
            finding={finding}
            review={review}
            getReview={getReview}
            segment={segment}
            variant={variant}
            selected={review.selectedFindingId === finding.finding_id}
            disabled={review.dirty || review.settingsDirty}
            fictional={variant === 'preview' && Boolean(review.preview?.fictional_finding_ids?.includes(finding.finding_id))}
          />
        )
      }} />
    </div>
  )
}
