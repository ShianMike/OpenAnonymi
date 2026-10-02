import { FileText, Eye, ListFilter } from 'lucide-react'
import type { ReviewController } from './useReviewController'
import { ReviewSource } from './ReviewSource'
import { ReviewPreview } from './ReviewPreview'
import * as Tabs from '@radix-ui/react-tabs'
import { KeyboardReview } from '../keyboard/KeyboardReview'

export function ReviewDocument({ review, userId }: { review: ReviewController; userId: string }) {
  return (
    <div className="review-text-column">
      <div className="document-toolbar">
        <Tabs.Root
          className="review-view-tabs"
          value={review.mobilePanel}
          onValueChange={(panel) => review.setMobilePanel(panel as typeof review.mobilePanel)}
        >
          <Tabs.List className="review-panel-switch" aria-label="Review views">
            {(
              [
                ['original', 'Original', FileText],
                ['preview', 'Reviewed output', Eye],
                ['findings', 'Findings', ListFilter],
              ] as const
            ).map(([panel, label, Icon]) => (
              <Tabs.Trigger
                key={panel}
                value={panel}
                className={panel === 'findings' ? 'review-tab-findings' : undefined}
                id={`review-${panel}-tab`}
                aria-controls={`review-${panel}-panel`}
              >
                <Icon size={15} strokeWidth={1.7} aria-hidden="true" />
                <span>{label}</span>
                {panel === 'findings' && <small>{review.activeFindings.length}</small>}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </Tabs.Root>
        <KeyboardReview key={`${userId}.${review.documentId}`} review={review} userId={userId} compact />
        {review.dirty && <span className="document-unsaved">Unsaved edits</span>}
      </div>
      <ReviewSource review={review} />
      <ReviewPreview review={review} />
    </div>
  )
}
