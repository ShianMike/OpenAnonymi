import { ArrowDown, Check, ChevronDown, Crosshair, Plus } from 'lucide-react'
import { categoryPresentation, findingCategories } from '../rules/categoryPresentation'
import { StudioSelect } from './studio/StudioControls'
import type { ReviewController } from './useReviewController'
import { FindingAdvanced } from './findings/FindingAdvanced'
import { StyleControls } from './StyleControls'
import { useWindowedList } from './useWindowedList'

export function ReviewFindings({ review }: { review: ReviewController }) {
  const { enabled, entries, containerRef, listRef, registerRow, onFocusCapture, onBlurCapture } = useWindowedList(review.visibleFindings, review.selectedFindingId)
  if (review.state.kind !== 'ready') return null
  const total = review.activeFindings.length
  const decided = total - review.pendingFindings.length
  return <section className={`studio-findings${enabled ? ' review-findings-windowed' : ''}`} ref={containerRef} id="review-findings-panel" aria-label="Findings to review">
    <div className="studio-review-progress"><span>{decided} of {total} reviewed</span><span>{total ? Math.round(decided / total * 100) : 0}%</span>
      <progress value={decided} max={Math.max(1, total)} aria-label="Finding review progress" /></div>
    <div className="studio-finding-toolbar"><details className="studio-filters" id="review-finding-filters"><summary>Filter <ChevronDown size={13} /></summary>
      <div className="studio-filter-fields"><label htmlFor="finding-category-filter">Category</label><StudioSelect id="finding-category-filter" value={review.categoryFilter} onValueChange={value => review.setCategoryFilter(value as typeof review.categoryFilter)}>
        <option value="all">All categories</option>{findingCategories.map(category => <option key={category} value={category}>{categoryPresentation[category].label}</option>)}</StudioSelect>
        <label htmlFor="finding-decision-filter">Decision</label><StudioSelect id="finding-decision-filter" value={review.decisionFilter} onValueChange={value => review.setDecisionFilter(value as typeof review.decisionFilter)}>
          <option value="all">All decisions</option><option value="pending">Needs review</option><option value="decided">Reviewed</option>
        </StudioSelect></div>
    </details><button type="button" onClick={review.nextUnresolved} disabled={!review.pendingFindings.length || review.decisionBlocked || review.dirty || review.settingsDirty || review.conflict}>Next unresolved <ArrowDown size={13} /></button></div>
    {!!review.findings?.overlaps.length && <p role="alert" className="studio-error">{review.findings.overlaps.length} overlapping ranges need correction or removal.</p>}
    {!total && <div className="studio-findings-empty"><Crosshair size={24} strokeWidth={1.3} /><h3>{review.scan?.status === 'completed' ? 'No details flagged' : 'Your findings appear here'}</h3><p>{review.scan?.status === 'completed' ? 'Read the full document and mark anything the check missed.' : 'Run a check to find details you may want to protect.'}</p></div>}
    {total > 0 && !review.visibleFindings.length && <p className="studio-findings-empty">No findings match these filters.</p>}
    <ol className={`studio-finding-list${enabled ? ' finding-list-windowed' : ''}`} ref={listRef} onFocusCapture={onFocusCapture} onBlurCapture={onBlurCapture}>
      {entries.map(entry => {
        if (entry.kind === 'spacer') return <li key={`spacer-${entry.key}`} className="finding-list-spacer" aria-hidden="true" style={{ height: entry.height }} />
        const { item, index } = entry
        const selected = review.selectedFindingId === item.finding_id
        const saving = review.pendingDecisionIds.includes(item.finding_id)
        return <li key={item.finding_id} id={`finding-${item.finding_id}`} ref={node => registerRow(item.finding_id, node)} data-window-finding={item.finding_id} aria-setsize={review.visibleFindings.length} aria-posinset={index + 1} data-selected={selected || undefined}>
          <button type="button" className="studio-finding-row" aria-expanded={selected} aria-controls={`decision-${item.finding_id}`} onClick={() => review.setSelectedFindingId(selected ? null : item.finding_id)}>
            <span className="studio-finding-number">{item.action ? <Check size={14} /> : String(index + 1).padStart(2, '0')}</span><span className="studio-finding-value"><span>{categoryPresentation[item.category].label}<small>{saving ? 'Saving…' : item.action === 'label' ? 'Replaced' : item.action === 'redact' ? 'Hidden' : item.action === 'keep' ? 'Kept' : 'Needs review'}<ChevronDown size={14} /></small></span><strong>{review.codePoints.slice(item.span.start, item.span.end).join('')}</strong></span>
          </button>
          {selected && <div className="studio-finding-detail" id={`decision-${item.finding_id}`}><button type="button" className="studio-locate" disabled={review.dirty || review.settingsDirty} onClick={() => review.locateFinding(item.finding_id, 'source')}><Crosshair size={13} /> Locate in document</button>
            <StyleControls finding={item} review={review} onApplied={() => {
              review.setSelectedFindingId(null)
              requestAnimationFrame(() => document.getElementById(`finding-${item.finding_id}`)?.querySelector<HTMLButtonElement>('.studio-finding-row')?.focus({ preventScroll: true }))
            }} />
            <FindingAdvanced item={item} review={review} />
          </div>}
        </li>
      })}
    </ol>
    <button type="button" className="studio-mark-manual" disabled={review.actionPending} onClick={() => {
      review.setEditingSource(true); review.setMobilePanel('original'); requestAnimationFrame(() => review.sourceRef.current?.focus())
    }}><Plus size={15} /> Mark a detail manually</button>
  </section>
}
