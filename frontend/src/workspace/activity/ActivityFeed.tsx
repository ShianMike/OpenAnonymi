import { useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import type { ActivityView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ActivityEmpty, ActivityPagination, ActivityTimeline } from './ActivityTimeline'
import { activityWindow, matchesEvent, periodLabel, type ActivityFilter, type ActivityOutcome, type DocumentMap } from './activityPresentation'

export function ActivityFeed({ value, documents, workspaceId }: {
  value: ActivityView
  documents: DocumentMap
  workspaceId: string
}) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ActivityFilter>('all')
  const [outcome, setOutcome] = useState<ActivityOutcome>('all')
  const [page, setPage] = useState(0)
  const searchInput = useRef<HTMLInputElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const filtered = value.own_events.filter(event => matchesEvent(event, documents, search, filter, outcome))
  const window = activityWindow(filtered.length, page)
  const hasFilters = !!search.trim() || filter !== 'all' || outcome !== 'all'
  const clear = () => { setSearch(''); setFilter('all'); setOutcome('all'); setPage(0); searchInput.current?.focus() }
  return <div className="activity-feed">
    <div className="activity-view-intro"><div><h2 ref={heading} tabIndex={-1}>Your recent activity</h2><p>Your actions and events on reviews you own.</p></div><span>Last 30 days</span></div>
    <div className="activity-filter-bar">
      <div className="activity-search-field">
          <Search size={15} aria-hidden="true" />
          <input ref={searchInput} aria-label="Search activity" type="search" placeholder="Search actions or reviews…"
            value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} autoComplete="off" />
          {search && <button type="button" className="activity-search-clear" aria-label="Clear search" onClick={() => { setSearch(''); setPage(0); searchInput.current?.focus() }}>
            <X size={14} aria-hidden="true" />
          </button>}
      </div>
        <GlassSelect id="activity-category" aria-label="Event category" value={filter} onValueChange={value => { setFilter(value as ActivityFilter); setPage(0) }}>
          <option value="all">All categories</option>
          <option value="reviews">Review actions</option>
          <option value="outputs">Copies & downloads</option>
          <option value="workspace">Workspace & security</option>
        </GlassSelect>
        <GlassSelect id="activity-result" aria-label="Event result" value={outcome} onValueChange={value => { setOutcome(value as ActivityOutcome); setPage(0) }}>
          <option value="all">All results</option><option value="completed">Completed</option><option value="failed">Failed</option>
        </GlassSelect>
        {hasFilters && <button type="button" className="activity-reset" onClick={clear}>Reset</button>}
    </div>
    {value.own_events.length < value.own_total && <p className="activity-limit-note">Search and filters cover the latest {value.own_events.length} of {value.own_total} events from the last 30 days.</p>}
    {filtered.length ? <><ActivityTimeline events={filtered.slice(window.start, window.end)}
      documents={documents} workspaceId={workspaceId} asOf={value.as_of} />
      <ActivityPagination page={window.page} total={filtered.length} onPrevious={() => { setPage(window.page - 1); heading.current?.focus() }} onNext={() => { setPage(window.page + 1); heading.current?.focus() }} />
    </> : <ActivityEmpty filtered={hasFilters} onClear={clear} workspaceId={workspaceId} />}
    <p className="activity-scope">
      {periodLabel(value.since)} – {periodLabel(value.as_of)}<span>Newest first · Select an event to inspect it</span>
    </p>
  </div>
}
