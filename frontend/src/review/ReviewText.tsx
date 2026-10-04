import { useMemo } from 'react'
import type { ReviewController } from './useReviewController'
import { FindingPopover } from './FindingPopover'
import { segmentText, type TextMark } from './textSegments'

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
      {segments.map((segment) => {
        const finding = segment.findings[0]
        if (!finding) return segment.text
        return (
          <FindingPopover
            key={`${finding.finding_id}-${segment.start}`}
            finding={finding}
            review={review}
          >
            <button
              type="button"
              id={`mark-${variant}-${finding.finding_id}-${segment.start}`}
              className="inline-finding"
              data-finding-id={finding.finding_id}
              data-action={finding.action || 'pending'}
              aria-label={`${finding.category}: ${segment.text}. ${finding.action || 'Needs decision'}.${variant === 'preview' && review.preview?.fictional_finding_ids?.includes(finding.finding_id) ? ' Fictional stand-in.' : ''} Open options`}
              data-selected={review.selectedFindingId === finding.finding_id || undefined}
              disabled={review.dirty || review.settingsDirty}
            >
              {segment.text}
            </button>
          </FindingPopover>
        )
      })}
    </div>
  )
}
