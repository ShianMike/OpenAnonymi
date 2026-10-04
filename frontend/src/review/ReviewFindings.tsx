import { categoryPresentation, findingCategories } from '../rules/categoryPresentation'
import { CategoryBadge } from '../rules/CategoryBadge'
import { ArrowRight, RotateCcw, ListFilter, Plus, ChevronDown, Sparkles } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import type { ReviewController } from './useReviewController'
import { FindingPopover } from './FindingPopover'
import { FindingAdvanced } from './findings/FindingAdvanced'
import { useWindowedList } from './useWindowedList'

export function ReviewFindings({ review }: { review: ReviewController }) {
  const { enabled, entries, containerRef, listRef, registerRow, onFocusCapture, onBlurCapture } =
    useWindowedList(review.visibleFindings, review.selectedFindingId)
  if (review.state.kind !== 'ready') return null
  const blocked = review.dirty || review.settingsDirty || review.actionPending || review.conflict
  const total = review.activeFindings.length
  const decided = total - review.pendingFindings.length
  return (
    <section
      className={`review-findings${enabled ? ' review-findings-windowed' : ''}`}
      ref={containerRef}
      id="review-findings-panel"
      aria-labelledby="findings-heading"
    >
      <div className="findings-heading">
        <div>
          <span className="review-eyebrow">YOUR DECISIONS</span>
          <h2 id="findings-heading">Current findings</h2>
        </div>
        <span className="findings-total">{total}</span>
      </div>
      <p className="findings-count" role="status">
        {total ? `${decided} of ${total} reviewed` : 'No details marked yet'}
        <span>
          {review.pendingFindings.length
            ? `${review.pendingFindings.length} to go`
            : total
              ? 'All decided'
              : ''}
        </span>
      </p>
      <div
        className="findings-progress"
        role="progressbar"
        aria-label="Finding review progress"
        aria-valuemin={0}
        aria-valuemax={Math.max(1, total)}
        aria-valuenow={decided}
      >
        <span style={{ width: `${total ? (decided / total) * 100 : 0}%` }} />
      </div>
      <div className="findings-tools">
        <button
          type="button"
          className="button-primary"
          onClick={review.nextUnresolved}
          disabled={!review.pendingFindings.length || blocked}
        >
          Next unresolved <ArrowRight size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="quiet-icon"
          onClick={() => void review.undoReview()}
          disabled={!review.undoCount || blocked}
          aria-label="Undo last review edit"
        >
          <RotateCcw size={16} aria-hidden="true" />
        </button>
      </div>
      <details className="finding-filter-details" id="review-finding-filters">
        <summary>
          <ListFilter size={15} aria-hidden="true" /> Filter findings{' '}
          <ChevronDown size={14} aria-hidden="true" />
        </summary>
        <div className="finding-filter-grid">
          <div>
            <label htmlFor="finding-category-filter">Category filter</label>
            <GlassSelect
              id="finding-category-filter"
              value={review.categoryFilter}
              onValueChange={(value) =>
                review.setCategoryFilter(value as typeof review.categoryFilter)
              }
            >
              {['all', ...findingCategories].map((category) => (
                <option key={category} value={category}>
                  {category === 'all'
                    ? 'All categories'
                    : categoryPresentation[category as keyof typeof categoryPresentation].label}
                </option>
              ))}
            </GlassSelect>
          </div>
          <div>
            <label htmlFor="finding-decision-filter">Decision filter</label>
            <GlassSelect
              id="finding-decision-filter"
              value={review.decisionFilter}
              onValueChange={(value) =>
                review.setDecisionFilter(value as typeof review.decisionFilter)
              }
            >
              <option value="all">All decisions</option>
              <option value="pending">Pending</option>
              <option value="decided">Decided</option>
            </GlassSelect>
          </div>
        </div>
      </details>
      {review.findings && review.findings.overlaps.length > 0 && (
        <p role="alert">
          {review.findings.overlaps.length} overlapping ranges need correction or removal.
        </p>
      )}
      {total === 0 && (
        <div className="findings-empty">
          <Sparkles size={24} strokeWidth={1.3} aria-hidden="true" />
          <p>
            {review.scan?.status === 'completed'
              ? 'No findings. Read the full text and mark any details worth a closer look.'
              : 'Run a scan to find possible sensitive details.'}
          </p>
        </div>
      )}
      {total > 0 && !review.visibleFindings.length && <p>No findings match these filters.</p>}
      <ol className={`finding-list${enabled ? ' finding-list-windowed' : ''}`} role="list"
        ref={listRef} onFocusCapture={onFocusCapture} onBlurCapture={onBlurCapture}>
        {entries.map((entry) => {
          if (entry.kind === 'spacer') return <li key={`spacer-${entry.key}`} className="finding-list-spacer"
            role="presentation" aria-hidden="true" style={{ height: entry.height }} />
          const { item, index } = entry
          return (
          <li
            key={item.finding_id}
            id={`finding-${item.finding_id}`}
            ref={(node) => registerRow(item.finding_id, node)}
            data-window-finding={item.finding_id}
            role="listitem"
            aria-setsize={review.visibleFindings.length}
            aria-posinset={index + 1}
            aria-current={review.selectedFindingId === item.finding_id ? 'true' : undefined}
          >
            <FindingPopover finding={item} review={review}>
              <button type="button" className="finding-card-trigger">
                <span className="finding-card-top">
                  <CategoryBadge category={item.category} />
                  {review.preview?.fictional_finding_ids?.includes(item.finding_id) && <span className="fictional-badge"><Sparkles size={11} aria-hidden="true" /> Fictional</span>}
                  <span className="finding-state" data-action={item.action || 'pending'}>
                    {item.action === 'label'
                      ? 'Labeled'
                      : item.action === 'redact'
                        ? 'Redacted'
                        : item.action === 'keep'
                          ? 'Kept'
                          : 'Needs decision'}
                  </span>
                </span>
                <strong>{review.codePoints.slice(item.span.start, item.span.end).join('')}</strong>
                <span className="finding-card-bottom">
                  {item.origin === 'automatic' ? 'Suggested detail' : 'Marked by you'}{' '}
                  <span>
                    Review <ArrowRight size={13} aria-hidden="true" />
                  </span>
                </span>
              </button>
            </FindingPopover>
            <FindingAdvanced item={item} review={review} />
          </li>
          )
        })}
      </ol>
      <button
        type="button"
        className="findings-add"
        disabled={review.actionPending}
        onClick={() => {
          review.setEditingSource(true)
          review.setMobilePanel('original')
          requestAnimationFrame(() => review.sourceRef.current?.focus())
        }}
      >
        <Plus size={16} aria-hidden="true" /> Mark a detail yourself
      </button>
      <p className="findings-tip">
        Click any highlighted text or finding to label, redact, or keep it.
      </p>
      {Array.from(review.groupMembers.values()).some((members) => members.length > 1) && (
        <details className="linked-summary">
          <summary>Linked occurrences</summary>
          {Array.from(
            review.groupMembers,
            ([id, members]) =>
              members.length > 1 && (
                <p key={id}>
                  {members[0].label} · {members.length} occurrences
                </p>
              ),
          )}
        </details>
      )}
    </section>
  )
}
