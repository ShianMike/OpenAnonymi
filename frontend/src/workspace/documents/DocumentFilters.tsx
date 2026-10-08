import { useLayoutEffect, useRef, type RefObject } from 'react'
import { CheckCircle2, Files, ScanLine, Star, Search, X } from 'lucide-react'
import type { DocumentIndexView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { RefreshButton } from '../../ui/WorkspaceControls'
import { matchesStatus, type DocumentSort } from './documentPresentation'

export function DocumentFilters({
  items,
  visibleCount,
  search,
  status,
  sort,
  refreshing,
  pageRef,
  onSearch,
  onStatus,
  onSort,
  onRefresh,
}: {
  items: DocumentIndexView[]
  visibleCount: number
  search: string
  status: string
  sort: DocumentSort
  refreshing: boolean
  pageRef: RefObject<HTMLElement | null>
  onSearch: (value: string) => void
  onStatus: (value: string) => void
  onSort: (value: DocumentSort) => void
  onRefresh: () => void
}) {
  const controlsRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const controls = controlsRef.current
    const page = pageRef.current
    if (!controls || !page) return
    const topbar = document.querySelector('.app-topbar')
    const previousPadding = document.documentElement.style.scrollPaddingTop
    const measure = () => {
      const height = controls.getBoundingClientRect().height
      page.style.setProperty('--document-controls-height', `${height}px`)
      const header = topbar?.getBoundingClientRect().height ?? 78
      page.style.setProperty('--document-header-offset', `${header}px`)
      document.documentElement.style.scrollPaddingTop = `${header + height + 55}px`
    }
    const observer = new ResizeObserver(measure)
    observer.observe(controls)
    if (topbar) observer.observe(topbar)
    measure()
    return () => {
      observer.disconnect()
      document.documentElement.style.scrollPaddingTop = previousPadding
    }
  }, [pageRef])

  return (<>
    <div className="document-quick-filters" role="group" aria-label="Quick filters">
      {[
        { value: 'all', label: 'All documents', help: 'Your own and assigned reviews', Icon: Files },
        { value: 'needs_review', label: 'Needs review', help: 'Details waiting for your choice', Icon: ScanLine },
        { value: 'complete', label: 'Completed', help: 'Ready, copied, or downloaded', Icon: CheckCircle2 },
        { value: 'favorites', label: 'Favorites', help: 'Saved for quick access', Icon: Star },
      ].map(({ value, label, help, Icon }) => {
        const count = items.filter((item) => matchesStatus(item, value)).length
        return <button type="button" key={value} aria-label={`${label} ${count}`}
          aria-describedby={`document-view-${value}`} aria-pressed={status === value} onClick={() => onStatus(value)}>
          <span className="document-view-label"><span className="document-view-icon"><Icon size={18} aria-hidden="true" /></span>{label}</span>
          <span className="document-view-metric"><strong>{count}</strong><span id={`document-view-${value}`} className="document-view-help">{help}</span></span>
        </button>
      })}
    </div>
    <div
      ref={controlsRef}
      className="document-controls"
      role="region"
      aria-label="Document search and filters"
    >
      <div className="document-filter-fields">
        <div className="document-search-field">
          <label htmlFor="document-search">
            Search titles
          </label>
          <Search size={17} aria-hidden="true" />
          <input
            id="document-search"
            type="search"
            placeholder="Find a review by title…"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
          {search && (
            <button type="button" aria-label="Clear search" onClick={() => onSearch('')}>
              <X size={15} aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="document-status-field">
          <label htmlFor="document-status">
            Status
          </label>
          <GlassSelect id="document-status" value={status} onValueChange={onStatus}>
            <option value="all">All statuses</option>
            <option value="favorites">Favorites</option>
            <option value="needs_review" data-description="Findings still need your decision">
              Needs review
            </option>
            <option value="complete" data-description="Ready or already exported">
              Completed
            </option>
            <option value="draft" data-description="Saved and waiting for a scan">
              Draft
            </option>
            <option value="scanning" data-description="Looking for identifying details">
              Scanning
            </option>
            <option value="ready" data-description="Reviewed and ready to share">
              Ready
            </option>
            <option value="exported" data-description="A reviewed copy has been generated">
              Exported
            </option>
            <option value="failed" data-description="The scan needs another attempt">
              Failed
            </option>
            <option value="expired" data-description="The retention period has ended">
              Expired
            </option>
          </GlassSelect>
        </div>
        <div className="document-sort-field">
          <label htmlFor="document-sort">
            Sort
          </label>
          <GlassSelect
            id="document-sort"
            value={sort}
            onValueChange={(value) => onSort(value as DocumentSort)}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="expiring">Expiring first</option>
            <option value="title">Title</option>
          </GlassSelect>
        </div>
        <RefreshButton label="Refresh documents" pending={refreshing} onClick={onRefresh} />
      </div>
      <div className="document-results-line">
        <p role="status" aria-live="polite">
          {refreshing ? 'Refreshing…' : `Showing ${visibleCount} of ${items.length} documents.`}
        </p>
        <span className="document-owner-note">Only reviews you own or are asked to check</span>
        {(search || status !== 'all') && (
          <button
            type="button"
            onClick={() => {
              onSearch('')
              onStatus('all')
            }}
          >
            Clear filters <X size={12} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  </>)
}
