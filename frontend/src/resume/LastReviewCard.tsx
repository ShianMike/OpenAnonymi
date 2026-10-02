import { ArrowRight, BookOpen, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView } from '../api/client'
import { StatusBadge } from '../ui/StatusBadge'
import { documentLabel, relativeEdit } from '../workspace/documents/documentPresentation'
import { reviewNextStep } from './reviewQueue'

export function LastReviewCard({ item, now, workspaceId }: { item: DocumentIndexView | null; now: number; workspaceId: string }) {
  return <section className="continue-last" aria-labelledby="last-review-heading">
    <div className="continue-last-copy">
      <span className="continue-kicker"><BookOpen size={16} aria-hidden="true" /> {item ? 'Last opened in this browser' : 'Your next review'}</span>
      <h2 id="last-review-heading">{item ? documentLabel(item).replace(/^Example · /, '') : 'Choose a review to continue'}</h2>
      <p>{item ? reviewNextStep(item) : 'Choose a review below. Your place will be saved as you work.'}</p>
      {item && <div className="continue-last-meta">
        <span>{item.is_owner ? 'Your review' : 'Assigned to you'}</span>
        <StatusBadge status={item.status} />
        <span><Clock3 size={13} aria-hidden="true" /> Edited {relativeEdit(item.updated_at, now)}</span>
      </div>}
    </div>
    {item && <div className="continue-last-action">
      <Link className="button-primary" to={`/documents/${item.id}/edit`} state={{ fromContinue: true, workspaceId }}>
        Resume review <ArrowRight size={17} aria-hidden="true" />
      </Link>
      <small>Returns to your saved view and reading position.</small>
    </div>}
  </section>
}
