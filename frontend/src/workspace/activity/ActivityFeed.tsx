import { useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import type { ActivityView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ActivityEmpty, ActivityPagination, ActivityTimeline } from './ActivityTimeline'
import { activityWindow, matchesEvent, type ActivityFilter, type DocumentMap } from './activityPresentation'

export function ActivityFeed({ value, documents, workspaceId }: {
  value: ActivityView
  documents: DocumentMap
  workspaceId: string
}) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ActivityFilter>('all')
  const [page, setPage] = useState(0)
  const searchInput = useRef<HTMLInputElement>(null)
  const filtered = value.own_events.filter(event => matchesEvent(event, documents, search, filter))
  const window = activityWindow(filtered.length, page)
  const hasFilters = !!search.trim() || filter !== 'all'
  const clear = () => { setSearch(''); setFilter('all'); setPage(0); searchInput.current?.focus() }
  return <div className="activity-feed">
    <div className="activity-filter-bar">
      <div className="activity-search">
        <label htmlFor="activity-search">Search activity</label>
        <div className="activity-search-field">
          <Search size={16} aria-hidden="true" />
          <input ref={searchInput} id="activity-search" type="search" placeholder="Find an action or review…"
            value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} autoComplete="off" />
          {search && <button type="button" className="quiet-icon" aria-label="Clear search" onClick={() => { setSearch(''); setPage(0); searchInput.current?.focus() }}>
            <X size={16} aria-hidden="true" />
          </button>}
        </div>
      </div>
      <div className="activity-type-filter">
        <label htmlFor="activity-type">Event type</label>
        <GlassSelect id="activity-type" value={filter} onValueChange={value => { setFilter(value as ActivityFilter); setPage(0) }}>
          <option value="all">All events</option>
          <option value="reviews">Review actions</option>
          <option value="outputs">Copies & downloads</option>
          <option value="workspace">Workspace changes</option>
        </GlassSelect>
      </div>
    </div>
    <ActivityPagination page={window.page} total={filtered.length}
      onPrevious={() => setPage(window.page - 1)} onNext={() => setPage(window.page + 1)} />
    {filtered.length ? <ActivityTimeline events={filtered.slice(window.start, window.end)}
      documents={documents} workspaceId={workspaceId} asOf={value.as_of} /> : <ActivityEmpty filtered={hasFilters} onClear={clear} workspaceId={workspaceId} />}
    <p className="activity-scope">
      {value.own_events.length < value.own_total ? `Search covers the latest ${value.own_events.length} events. ` : ''}
      Your actions and activity on reviews you own. Most recent first.
    </p>
  </div>
}
