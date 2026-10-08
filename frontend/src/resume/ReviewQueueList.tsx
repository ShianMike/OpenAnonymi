import { useRef, useState } from 'react'
import { ArrowUpRight, FileText, UserRoundCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView } from '../api/client'
import { StatusBadge } from '../ui/StatusBadge'
import { documentLabel, relativeEdit } from '../workspace/documents/documentPresentation'
import { reviewNextStep } from './reviewQueue'

export function ReviewQueueList({ items, assigned, now, workspaceId }: {
  items: DocumentIndexView[]; assigned?: boolean; now: number; workspaceId: string
}) {
  const [limit, setLimit] = useState(4)
  const listRef = useRef<HTMLUListElement>(null)
  const headingId = assigned ? 'assigned-reviews-heading' : 'your-unfinished-heading'
  const Icon = assigned ? UserRoundCheck : FileText
  return (
    <section className="continue-queue" aria-labelledby={headingId}>
      <header className="continue-queue-heading">
        <span className="continue-symbol"><Icon size={18} aria-hidden="true" /></span>
        <div>
          <h2 id={headingId}>{assigned ? 'Shared with you' : 'Your unfinished reviews'} <small>{items.length}</small></h2>
          <p>{assigned ? 'Reviews a teammate asked you to check.' : 'Choose a review to see what needs doing next.'}</p>
        </div>
      </header>
      {items.length === 0 ? (
        <div className="continue-queue-empty">
          <span className="continue-symbol"><Icon size={20} aria-hidden="true" /></span>
          <strong>{assigned ? 'Nothing shared with you yet' : 'You’re all caught up'}</strong>
          <p>{assigned ? 'When a teammate invites you to review, it will appear here.' : 'Your finished reviews are in Documents. You can start a new one whenever you’re ready.'}</p>
          {!assigned && <Link className="continue-empty-action" to={`/new?workspace=${workspaceId}`}>Start a new review</Link>}
        </div>
      ) : <>
        <ul className="continue-review-list" ref={listRef}>
          {items.slice(0, limit).map((item) => <li key={item.id}>
            <Link to={`/documents/${item.id}/edit`} state={{ fromContinue: true, workspaceId }}
              aria-label={`Open ${documentLabel(item)}`}>
              <div className="continue-row-top">
                <strong>{documentLabel(item).replace(/^Example · /, '')}</strong>
                <ArrowUpRight size={16} aria-hidden="true" />
              </div>
              <p>{reviewNextStep(item)}</p>
              <div className="continue-row-meta">
                <StatusBadge status={item.status} />
                <span>{Math.min(item.decided_count, item.finding_count)} of {item.finding_count} checked</span>
                <time dateTime={item.updated_at}>Edited {relativeEdit(item.updated_at, now)}</time>
              </div>
            </Link>
          </li>)}
        </ul>
        {items.length > limit && <button className="continue-show-more" type="button"
          onClick={() => {
            const nextIndex = limit
            setLimit((value) => value + 4)
            requestAnimationFrame(() => listRef.current?.querySelectorAll('a')[nextIndex]?.focus())
          }}>
          Show more {assigned ? 'assigned' : 'unfinished'} reviews · {items.length - limit} remaining
        </button>}
      </>}
    </section>
  )
}
