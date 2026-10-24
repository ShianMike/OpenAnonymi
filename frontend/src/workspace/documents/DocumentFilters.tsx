import * as Tabs from '@radix-ui/react-tabs'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { ArrowDownWideNarrow, Check, ListFilter, RefreshCw, Search, SquareDashedMousePointer, X } from 'lucide-react'
import type { DocumentIndexView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { documentStatuses, documentViews, matchesDocumentView, type readDocumentQuery } from './documentPresentation'

export function DocumentFilters({ items, query, refreshing, disabled, selecting, canSelect, onToggleSelection, onChange, onRefresh }: {
  items: DocumentIndexView[] | undefined; query: ReturnType<typeof readDocumentQuery>; refreshing: boolean; disabled: boolean
  selecting: boolean; canSelect: boolean; onToggleSelection: () => void
  onChange: (name: string, value: string) => void; onRefresh: () => void
}) {
  const statusLabel = documentStatuses.find(item => item.value === query.status)?.label
  return <>
    <Tabs.List className="document-views" aria-label="Document views">
      {documentViews.map(view => <Tabs.Trigger key={view.value} value={view.value}>
        {view.label}{items && <span>{items.filter(item => matchesDocumentView(item, view.value)).length}</span>}
      </Tabs.Trigger>)}
    </Tabs.List>
    <div className="document-toolbar" role="region" aria-label="Document search and filters">
      <div className="document-search">
        <Search size={16} aria-hidden="true" /><label htmlFor="document-search" className="sr-only">Search documents</label>
        <input id="document-search" type="search" maxLength={200} placeholder="Search documents…" value={query.search}
          onChange={event => onChange('q', event.target.value)} />
        {query.search && <button type="button" className="document-icon-button" aria-label="Clear search" onClick={() => onChange('q', '')}><X size={14} /></button>}
        <button type="button" className="document-icon-button" aria-label="Refresh documents" title="Refresh documents" aria-busy={refreshing} disabled={disabled || refreshing} onClick={onRefresh}>
          <RefreshCw size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="document-toolbar-actions">
        <Menu.Root>
          <Menu.Trigger className="document-filter-trigger" data-active={query.status !== 'all' || undefined}>
            <ListFilter size={15} aria-hidden="true" /><span>{query.status === 'all' ? 'Filter' : statusLabel}</span>
            {query.status !== 'all' && <small>1</small>}
          </Menu.Trigger>
          <Menu.Portal><Menu.Content className="document-action-menu" align="end" sideOffset={6} collisionPadding={12}>
            <Menu.Label className="document-menu-label">Review status</Menu.Label>
            <Menu.RadioGroup value={query.status} onValueChange={value => onChange('status', value)}>
              {documentStatuses.map(item => <Menu.RadioItem key={item.value} value={item.value}>
                <span>{item.label}</span><Menu.ItemIndicator><Check size={14} aria-hidden="true" /></Menu.ItemIndicator>
              </Menu.RadioItem>)}
            </Menu.RadioGroup>
          </Menu.Content></Menu.Portal>
        </Menu.Root>
        <ArrowDownWideNarrow size={15} className="document-sort-icon" aria-hidden="true" />
        <GlassSelect id="document-sort" aria-label="Sort documents" value={query.sort} className="document-sort" onValueChange={value => onChange('sort', value)}>
          <option value="updated">Last updated</option><option value="newest">Newest created</option>
          <option value="oldest">Oldest created</option><option value="title">Title A–Z</option><option value="expiring">Expiring soon</option>
        </GlassSelect>
        <button id="document-select-mode" type="button" className="document-selection-toggle" aria-pressed={selecting} aria-controls="document-gallery"
          title={selecting ? 'Exit selection mode' : 'Select documents for a bulk action'} disabled={disabled || (!selecting && !canSelect)} onClick={onToggleSelection}>
          <SquareDashedMousePointer size={15} aria-hidden="true" />Select
        </button>
      </div>
    </div>
  </>
}
