import type { ReviewController } from '../review/useReviewController'

export function readReviewedOutput(review: ReviewController) {
  review.setMobilePanel('preview')
  requestAnimationFrame(() => {
    const tab = document.getElementById('review-preview-tab')
    tab?.focus({ preventScroll: true })
    tab?.scrollIntoView({ block: 'start', behavior: 'instant' })
  })
}
