import { useEffect, useLayoutEffect, useRef, useState, type ComponentProps, type KeyboardEvent, type RefObject } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import { Command, useCommandState } from 'cmdk'
import { ArrowDown, ArrowRight, ArrowUp, CornerDownLeft, Pin, Search, Star, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiRequestError, searchDocuments, type DocumentSearchView, type SessionView } from '../api/client'
import { useReviewWorkspace } from '../resume/reviewWorkspace'
import { workspaceHref } from '../shell/navigation'
import { GlassSelect } from '../ui/GlassSelect'
import { InlineNotice } from '../ui/WorkspaceControls'
import { StatusBadge } from '../ui/StatusBadge'
import { LoadingState } from '../loading/LoadingState'
import { mergeSearchResults, searchPages, searchWorkspace, titleParts, type SearchView } from './searchPresentation'
import './search.css'

export function GlobalSearch({ session }: { session: SessionView }) {
  const [open, setOpen] = useState(false)
  const content = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function shortcut(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.isComposing && event.key.toLowerCase() === 'k') {
        if (!content.current && document.querySelector('[role="dialog"], [role="alertdialog"]')) return
        event.preventDefault(); setOpen(value => !value)
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger className="global-search-trigger" aria-label="Search documents and pages" aria-keyshortcuts="Control+K Meta+K" title="Search (Ctrl or Cmd + K)">
      <Search size={16} aria-hidden="true" /><span>Search…</span><kbd>Ctrl / ⌘ K</kbd>
    </Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="global-search-overlay" />
      <Dialog.Content className="global-search-dialog" ref={content} onOpenAutoFocus={event => {
        event.preventDefault(); content.current?.querySelector<HTMLInputElement>('[cmdk-input]')?.focus()
      }}>
        <Dialog.Title className="sr-only">Search</Dialog.Title>
        <Dialog.Description className="sr-only">Find accessible reviews by title or go to a page. Use the arrow keys to choose a result and Enter to open it.</Dialog.Description>
        <SearchContents key={`${session.user_id}.${session.csrf_token}.${session.memberships.map(item => `${item.workspace_id}:${item.role}`).join(',')}`} session={session} onClose={() => setOpen(false)} />
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}

// Keep toolbar controls' native keys out of the command list's keyboard handler.
function controlKeys(event: KeyboardEvent) {
  if (['Enter', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) event.stopPropagation()
}

function SearchTitle({ title, query }: { title: string; query: string }) {
  return titleParts(title, query).map((part, index) => index % 2 ? <mark key={index}>{part}</mark> : part)
}

function SearchInput({ inputRef, ...props }: ComponentProps<typeof Command.Input> & { inputRef: RefObject<HTMLInputElement | null> }) {
  const selected = useCommandState(state => state.value)
  const [activeId, setActiveId] = useState<string>()
  // Async items can register in cmdk before their selected DOM node is committed.
  useLayoutEffect(() => {
    setActiveId(inputRef.current?.closest('[cmdk-root]')?.querySelector('[cmdk-item][aria-selected=true]')?.id)
  }, [selected, inputRef])
  return <Command.Input {...props} ref={inputRef} asChild><input aria-activedescendant={activeId} /></Command.Input>
}

function SearchContents({ session, onClose }: { session: SessionView; onClose: () => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const preferred = useReviewWorkspace(session.user_id)
  const [query, setQuery] = useState('')
  const [view, setView] = useState<SearchView>('all')
  const [workspaceId, setWorkspaceId] = useState('')
  const [favorites, setFavorites] = useState(false)
  const [value, setValue] = useState<DocumentSearchView | null>(null)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const reviews = view !== 'pages'
  const workspace = searchWorkspace(session, workspaceId, new URLSearchParams(location.search).get('workspace'), preferred)
  const navigation = searchPages(query, view, workspace?.role === 'administrator')

  function clearResults() {
    generation.current += 1; controller.current?.abort()
    setValue(null); setError(null); setPending(true)
  }
  function retry() { clearResults(); setAttempt(current => current + 1); input.current?.focus() }
  function go(path: string) { onClose(); void navigate(path) }

  useEffect(() => {
    if (!reviews) return
    const active = new AbortController()
    controller.current = active
    const current = ++generation.current
    const timer = window.setTimeout(() => {
      searchDocuments({ query, workspace_id: workspaceId || null, favorites_only: favorites, limit: 20 }, session.csrf_token, active.signal)
        .then(result => { if (!active.signal.aborted && current === generation.current) setValue(result) })
        .catch((cause: unknown) => {
          if (!active.signal.aborted && current === generation.current) setError(cause instanceof Error ? cause.message : 'Search could not be completed.')
        })
        .finally(() => { if (!active.signal.aborted && current === generation.current) setPending(false) })
    }, 250)
    return () => { window.clearTimeout(timer); active.abort() }
  }, [query, workspaceId, favorites, reviews, attempt, session.csrf_token])

  async function more() {
    if (pending || !reviews || !value?.next_cursor) return
    setPending(true); setError(null)
    const active = new AbortController()
    controller.current?.abort(); controller.current = active
    const current = ++generation.current
    try {
      const result = await searchDocuments({ query, workspace_id: workspaceId || null, favorites_only: favorites, cursor: value.next_cursor, limit: 20 }, session.csrf_token, active.signal)
      if (!active.signal.aborted && current === generation.current) setValue(previous => mergeSearchResults(previous, result))
    } catch (cause) {
      if (!active.signal.aborted && current === generation.current) {
        if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) setValue(null)
        setError(cause instanceof Error ? cause.message : 'More reviews could not be searched.')
      }
    } finally { if (!active.signal.aborted && current === generation.current) setPending(false) }
  }
  useEffect(() => () => { controller.current?.abort(); generation.current += 1 }, [])

  const title = query.trim() ? 'Matching reviews' : favorites ? 'Favorite reviews' : 'Recent reviews'
  const hasResults = navigation.length > 0 || reviews && !!(value?.items.length || value?.next_cursor)
  const destinations = navigation.length > 0 && <Command.Group heading={<>{view === 'all' && !query.trim() ? 'Quick navigation' : 'Pages'}<span>{workspace?.workspace_name || 'Your account'}</span></>}>
    {navigation.map(page => <Command.Item className="search-page-result" key={page.path} value={`page:${page.path}`} onSelect={() => go(page.path === '/preferences' ? '/settings?section=appearance' : workspaceHref(page.path, workspace?.workspace_id))}>
      <page.icon size={17} strokeWidth={1.6} aria-hidden="true" /><span className="search-result-copy"><strong><SearchTitle title={page.name} query={query} /></strong>{view === 'pages' && <small>{page.description}</small>}</span><ArrowRight className="search-page-arrow" size={15} aria-hidden="true" />
    </Command.Item>)}
  </Command.Group>
  return <Command className="search-command" label="Search reviews and pages" shouldFilter={false} loop vimBindings={false}>
    <header className="search-input-row"><Search size={20} strokeWidth={1.6} aria-hidden="true" />
      <SearchInput inputRef={input} autoComplete="off" spellCheck={false} maxLength={100}
        value={query} onValueChange={next => { clearResults(); setQuery(next) }} placeholder="Search reviews and pages…" />
      {query && <button type="button" className="search-clear" aria-label="Clear search" onKeyDown={controlKeys} onClick={() => { clearResults(); setQuery(''); input.current?.focus() }}><X size={15} aria-hidden="true" /></button>}
      <Dialog.Close className="search-close" aria-label="Close search" onKeyDown={controlKeys}><span>Esc</span><X size={17} aria-hidden="true" /></Dialog.Close>
    </header>
    <Tabs.Root className="search-body" value={view} onValueChange={next => {
      if ((next === 'pages') !== !reviews) clearResults()
      setView(next as SearchView)
    }}>
      <div className="search-toolbar" onKeyDown={controlKeys}>
        <Tabs.List className="search-views" aria-label="Search in"><Tabs.Trigger value="all">All</Tabs.Trigger><Tabs.Trigger value="reviews">Reviews</Tabs.Trigger><Tabs.Trigger value="pages">Pages</Tabs.Trigger></Tabs.List>
        <div className="search-filters"><GlassSelect id="search-workspace" value={workspaceId} aria-label="Search workspace" onValueChange={next => { clearResults(); setWorkspaceId(next) }}>
          <option value="">All workspaces</option>{session.memberships.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}
        </GlassSelect>{reviews && <button className="search-favorites" type="button" aria-label="Favorite reviews only" aria-pressed={favorites} onClick={() => { clearResults(); setFavorites(current => !current) }}><Star size={14} aria-hidden="true" /><span>Favorites</span></button>}</div>
      </div>
      <Tabs.Content className="search-panel" value={view} tabIndex={-1}>
        <Command.List className="search-results" label="Search results" aria-busy={reviews && pending}>
          {!query.trim() && destinations}
          {reviews && <Command.Group heading={<>{title}{value && <span>{value.items.length}{value.next_cursor ? '+' : ''}</span>}</>}>
            {pending && !value && <LoadingState label="Searching review titles…" compact />}
            {value?.items.map(item => <Command.Item className="search-review-result" key={item.id} value={`review:${item.id}`} onSelect={() => go(`/documents/${item.id}/edit`)}>
              <span className="search-result-copy"><strong><SearchTitle title={item.title || 'Untitled review'} query={query} /></strong><small>{item.workspace_name || 'Workspace'}{!item.is_owner && <span>Shared with you</span>}{item.favorite && <Star size={12} aria-label="Favorite" />}{item.pinned && <Pin size={12} aria-label="Pinned" />}</small></span>
              <StatusBadge status={item.status} /><CornerDownLeft className="search-result-enter" size={15} aria-hidden="true" />
            </Command.Item>)}
            {!pending && !error && value?.items.length === 0 && <div className="search-empty"><strong>{value.next_cursor ? 'No matches in this batch' : favorites ? 'No matching favorites' : query.trim() ? 'No matching reviews' : 'No reviews yet'}</strong><p>{value.next_cursor ? 'Continue searching older reviews below.' : favorites ? 'Turn off Favorites to search all accessible reviews.' : query.trim() ? 'Try a different title or choose Pages to find a destination.' : 'Start a new review with text or a file.'}</p>{favorites && !value.next_cursor && <button type="button" onKeyDown={controlKeys} onClick={() => { clearResults(); setFavorites(false); input.current?.focus() }}>Clear favorites filter</button>}{!favorites && !query.trim() && !value.next_cursor && <button type="button" onKeyDown={controlKeys} onClick={() => go(workspaceHref('/new', workspace?.workspace_id))}>New review</button>}</div>}
            {value?.next_cursor && <Command.Item className="search-load-more" value="more" disabled={pending} onSelect={() => void more()}>{pending ? 'Searching older reviews…' : 'Search older reviews'}<ArrowDown size={14} aria-hidden="true" /></Command.Item>}
          </Command.Group>}
          {!!query.trim() && destinations}
          {view === 'pages' && !navigation.length && <div className="search-empty"><strong>No matching pages</strong><p>Try a page name such as Documents, Settings or Appearance.</p></div>}
        </Command.List>
        {reviews && error && <div className="search-error" onKeyDown={controlKeys}><InlineNotice error title="Review search is unavailable" actions={<button type="button" onClick={retry}>Try again</button>}>{error} Page navigation is still available.</InlineNotice></div>}
      </Tabs.Content>
    </Tabs.Root>
    <footer className="search-footer"><span className="search-privacy">{view === 'pages' ? 'Go to a page' : 'Reviews are searched by title'}</span>{hasResults && <div><span><kbd><ArrowUp size={11} /><ArrowDown size={11} /></kbd> Navigate</span><span><kbd>↵</kbd> Open</span></div>}</footer>
    <span className="sr-only" role="status" aria-live="polite">{reviews ? pending ? 'Searching reviews' : error ? 'Review search unavailable' : `${value?.items.length ?? 0}${value?.next_cursor ? ' or more' : ''} ${value?.items.length === 1 && !value.next_cursor ? 'review' : 'reviews'} found` : `${navigation.length} ${navigation.length === 1 ? 'page' : 'pages'} found`}</span>
  </Command>
}
