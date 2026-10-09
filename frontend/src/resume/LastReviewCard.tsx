import { ArrowRight, BookOpen, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView } from '../api/client'
import { StatusBadge } from '../ui/StatusBadge'
import { documentLabel, relativeEdit } from '../workspace/documents/documentPresentation'
import { reviewNextStep } from './reviewQueue'

export function LastReviewCard({ item, now, workspaceId }: { item: DocumentIndexView | null; now: number; workspaceId: string }) {
  if (!item) return null
  return <section className="continue-last" aria-labelledby="last-review-heading">
    <div className="continue-last-copy">
      <span className="continue-kicker"><BookOpen size={16} aria-hidden="true" /> Pick up where you left off</span>
      <h2 id="last-review-heading">{documentLabel(item).replace(/^Example · /, '')}</h2>
      <p>{reviewNextStep(item)}</p>
      <div className="continue-last-meta">
        <span>{item.is_owner ? 'Your review' : 'Assigned to you'}</span>
        <StatusBadge status={item.status} />
        <span><Clock3 size={13} aria-hidden="true" /> Edited {relativeEdit(item.updated_at, now)}</span>
      </div>
    </div>
    <div className="continue-last-action">
      <Link className="button-primary" to={`/documents/${item.id}/edit`} state={{ fromContinue: true, workspaceId }}>
        Resume review <ArrowRight size={17} aria-hidden="true" />
      </Link>
      <small>Your saved place is remembered.</small>
    </div>
  </section>
}
