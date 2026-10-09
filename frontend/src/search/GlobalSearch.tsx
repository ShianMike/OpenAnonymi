import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowRight, FileText, Pin, Search, Star, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiRequestError, searchDocuments, type DocumentSearchView, type SessionView } from '../api/client'
import { pages, workspaceHref } from '../shell/navigation'
import { useReviewWorkspace } from '../resume/reviewWorkspace'
import { ListPagination } from '../ui/ListPagination'
import { pageWindow } from '../ui/pagination'
import './search.css'

export function GlobalSearch({ session }: { session: SessionView }) {
  const [open, setOpen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function shortcut(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  function arrows(event: KeyboardEvent<HTMLElement>) {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLAnchorElement>('.search-results a'))
    if (!targets.length) return
    const index = targets.indexOf(event.target as HTMLAnchorElement)
    if (index < 0 && (event.target as HTMLElement).id !== 'global-document-search') return
    event.preventDefault()
    const next = index < 0 ? (event.key === 'ArrowDown' ? 0 : targets.length - 1)
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + targets.length) % targets.length
    targets[next]?.focus()
  }
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger className="global-search-trigger" aria-label="Search documents and pages" aria-keyshortcuts="Control+K Meta+K" title="Search documents and pages (Ctrl or Cmd + K)">
      <Search size={18} aria-hidden="true" /><span>Search reviews or pages</span><kbd>Ctrl / ⌘ K</kbd>
    </Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="global-search-overlay" />
      <Dialog.Content className="global-search-dialog" ref={contentRef} onKeyDown={arrows}
        onOpenAutoFocus={(event) => { event.preventDefault(); contentRef.current?.querySelector<HTMLInputElement>('#global-document-search')?.focus() }}>
        <SearchContents session={session} onClose={() => setOpen(false)} />
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}

function SearchContents({ session, onClose }: { session: SessionView; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [favorites, setFavorites] = useState(false)
  const [value, setValue] = useState<DocumentSearchView | null>(null)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [page, setPage] = useState(0)
  const preferred = useReviewWorkspace(session.user_id)
  const controller = useRef<AbortController | null>(null)
  const generation = useRef(0)

  function clearResults() {
    generation.current += 1
    controller.current?.abort()
    setValue(null)
    setError(null)
    setPending(true)
    setPage(0)
  }

  useEffect(() => {
    const active = new AbortController()
    controller.current = active
    const current = ++generation.current
    const timer = window.setTimeout(() => {
      searchDocuments({ query, favorites_only: favorites, limit: 20 }, session.csrf_token, active.signal)
        .then((result) => { if (!active.signal.aborted && current === generation.current) setValue(result) })
        .catch((cause: unknown) => {
          if (!active.signal.aborted && current === generation.current) setError(cause instanceof Error ? cause.message : 'Search could not be completed.')
        })
        .finally(() => { if (!active.signal.aborted && current === generation.current) setPending(false) })
    }, 250)
    return () => { window.clearTimeout(timer); active.abort() }
  }, [query, favorites, attempt, session.csrf_token])

  async function more() {
    if (pending) return
    if (range.end < (value?.items.length ?? 0)) { setPage(range.page + 1); return }
    if (!value?.next_cursor) return
    setPending(true)
    setError(null)
    const active = new AbortController()
    controller.current?.abort()
    controller.current = active
    const current = ++generation.current
    try {
      const result = await searchDocuments({ query, favorites_only: favorites, cursor: value.next_cursor, limit: 20 }, session.csrf_token, active.signal)
      if (!active.signal.aborted && current === generation.current) {
        setValue((previous) => previous ? {
          ...result, items: [...previous.items, ...result.items.filter((item) => !previous.items.some((old) => old.id === item.id))],
        } : result)
        setPage(Math.floor(range.end / 4))
      }
    } catch (cause) {
      if (!active.signal.aborted && current === generation.current) {
        if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) setValue(null)
        setError(cause instanceof Error ? cause.message : 'More documents could not be searched.')
      }
    } finally {
      if (!active.signal.aborted && current === generation.current) setPending(false)
    }
  }

  useEffect(() => () => { controller.current?.abort(); generation.current += 1 }, [])

  const navigation = pages.filter(page => page.name.toLowerCase().includes(query.trim().toLowerCase()) &&
    (page.path !== '/members' || session.memberships.some(item => item.role === 'administrator')))
  const range = pageWindow(value?.items.length ?? 0, page, 4)
  const workspaceId = session.memberships.find(item => item.workspace_id === preferred)?.workspace_id
  return <>
      <div className="global-search-header">
        <div className="global-search-heading"><Dialog.Title>Search</Dialog.Title>
          <Dialog.Close aria-label="Close search"><X size={18} aria-hidden="true" /></Dialog.Close>
        </div>
        <Dialog.Description>Find a review by title or jump to a page.</Dialog.Description>
        <label className="sr-only" htmlFor="global-document-search">Search documents and pages</label>
        <div className="global-search-field"><Search size={20} aria-hidden="true" />
          <input id="global-document-search" type="search" autoComplete="off" maxLength={100}
            value={query} onChange={(event) => { clearResults(); setQuery(event.target.value) }} placeholder="Type a review title or page…" />
        </div>
        <div className="global-search-scope"><span>All workspaces</span>
          <button className="search-favorites" type="button" aria-pressed={favorites} onClick={() => { clearResults(); setFavorites((current) => !current) }}>
            <Star size={16} aria-hidden="true" /> Favorites only
          </button>
        </div>
      </div>
      <div className="search-results" aria-busy={pending}>
        <section aria-label="Matching documents"><h2>{query.trim() ? 'Matching reviews' : favorites ? 'Your favorites' : 'Recent reviews'}</h2>
          {pending && !value && <p className="search-inline-status">Finding your reviews…</p>}
          {value && <ul className="search-document-list">{value.items.slice(range.start, range.end).map((item) => <li key={item.id}>
            <Link to={`/documents/${item.id}/edit`} onClick={onClose}><span className="search-result-icon"><FileText size={18} aria-hidden="true" /></span>
              <span className="search-document-copy"><strong>{item.title || 'Untitled review'}</strong><small>{item.workspace_name}{!item.is_owner && ' · Assigned to you'}</small></span>
              {item.favorite && <Star size={15} aria-label="Favorite" />}{item.pinned && <Pin size={15} aria-label="Pinned" />}
              <ArrowRight className="search-result-arrow" size={17} aria-hidden="true" />
            </Link></li>)}</ul>}
          {!pending && value?.items.length === 0 && <div className="search-empty"><Search size={22} aria-hidden="true" />
            <strong>{favorites ? 'No matching favorites' : 'No matching reviews'}</strong>
            <p>{value.next_cursor ? 'Use Next to keep looking.' : favorites ? 'Turn off Favorites only to see all your reviews.' : 'Try another title, or use a page shortcut below.'}</p>
          </div>}
        </section>
        {navigation.length > 0 && <section className="search-pages" aria-label="Pages"><h2>Go to a page</h2><ul>{navigation.map((page) =>
          <li key={page.path}><Link to={workspaceHref(page.path, workspaceId)} onClick={onClose}><page.icon size={17} aria-hidden="true" />{page.name}</Link></li>,
        )}</ul></section>}
        {error && <div className="search-error" role="alert"><p>{error}</p><button type="button" onClick={() => { clearResults(); setAttempt((current) => current + 1) }}>Retry search</button></div>}
      </div>
      <div className="global-search-footer">
        {value && <ListPagination label="Reviews" page={range.page} total={value.items.length} pageSize={4} hasMore={!!value.next_cursor} pending={pending}
          onPrevious={() => setPage(range.page - 1)} onNext={() => void more()} />}
        <small><span><kbd>↑</kbd><kbd>↓</kbd> Move</span><span><kbd>Enter</kbd> Open</span><span><kbd>Esc</kbd> Close</span></small>
        {(pending || error) && <span role="status">{pending ? 'Searching…' : 'Search unavailable'}</span>}
      </div>
  </>
}
