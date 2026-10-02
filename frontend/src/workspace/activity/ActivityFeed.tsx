import { useState } from 'react'
import { ArrowDown, Search, X } from 'lucide-react'
import type { ActivityView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ActivityEmpty, ActivityTimeline } from './ActivityTimeline'
import { matchesEvent, type ActivityFilter, type DocumentMap } from './activityPresentation'

export function ActivityFeed({
  value,
  documents,
  workspaceId,
}: {
  value: ActivityView
  documents: DocumentMap
  workspaceId: string
}) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ActivityFilter>('all')
  const [limit, setLimit] = useState(20)
  const filtered = value.own_events.filter((event) => matchesEvent(event, documents, search, filter))
  const hasFilters = !!search.trim() || filter !== 'all'
  const clear = () => {
    setSearch('')
    setFilter('all')
    setLimit(20)
  }
  return (
    <div className="activity-feed">
      <div className="activity-filter-bar">
        <div className="activity-search">
          <Search size={16} aria-hidden="true" />
          <label className="sr-only" htmlFor="activity-search">
            Search activity
          </label>
          <input
            id="activity-search"
            type="search"
            placeholder="Search activity or review titles…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setLimit(20)
            }}
            autoComplete="off"
          />
          {search && (
            <button
              type="button"
              className="quiet-icon"
              aria-label="Clear search"
              onClick={() => {
                setSearch('')
                setLimit(20)
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
        <label className="sr-only" htmlFor="activity-type">
          Event type
        </label>
        <GlassSelect
          id="activity-type"
          value={filter}
          onValueChange={(value) => {
            setFilter(value as ActivityFilter)
            setLimit(20)
          }}
        >
          <option value="all">All events</option>
          <option value="reviews">Review actions</option>
          <option value="outputs">Copies & downloads</option>
          <option value="workspace">Workspace changes</option>
        </GlassSelect>
      </div>
      <div className="activity-feed-caption">
        <h2>Your timeline</h2>
        <span aria-live="polite">
          {hasFilters ? `${filtered.length} matching events` : 'Most recent first'}
        </span>
      </div>
      {filtered.length ? (
        <ActivityTimeline
          events={filtered.slice(0, limit)}
          documents={documents}
          workspaceId={workspaceId}
          asOf={value.as_of}
        />
      ) : (
        <ActivityEmpty filtered={hasFilters} onClear={clear} />
      )}
      {!!filtered.length && (
        <div className="activity-feed-footer">
          <span>
            Showing {Math.min(limit, filtered.length)} of {filtered.length}
            {hasFilters ? ' matching' : ' loaded'} events
          </span>
          {limit < filtered.length && (
            <button
              type="button"
              className="quiet-button"
              onClick={() => setLimit((current) => current + 20)}
            >
              Show more <ArrowDown size={14} aria-hidden="true" />
            </button>
          )}
          {value.own_events.length < value.own_total && (
            <p>Search and filters apply to the latest {value.own_events.length} events loaded.</p>
          )}
        </div>
      )}
    </div>
  )
}
