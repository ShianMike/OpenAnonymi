import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { FileText, Pin, Search, Star, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiRequestError, searchDocuments, type DocumentSearchView, type SessionView } from '../api/client'
import { pages } from '../shell/navigation'
import './search.css'

export function GlobalSearch({ session }: { session: SessionView }) {
  const [open, setOpen] = useState(false)
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
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger className="global-search-trigger" aria-label="Search documents and pages" title="Search documents and pages (Ctrl or Cmd + K)">
      <Search size={17} aria-hidden="true" /><span>Search</span><kbd>Ctrl / ⌘ K</kbd>
    </Dialog.Trigger>
    {open && <SearchDialog session={session} onClose={() => setOpen(false)} />}
  </Dialog.Root>
}

function SearchDialog({ session, onClose }: { session: SessionView; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [favorites, setFavorites] = useState(false)
  const [value, setValue] = useState<DocumentSearchView | null>(null)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const contentRef = useRef<HTMLDivElement>(null)

  function clearResults() {
    generation.current += 1
    controller.current?.abort()
    setValue(null)
    setError(null)
    setPending(true)
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
    if (pending || !value?.next_cursor) return
    setPending(true)
    setError(null)
    const active = new AbortController()
    controller.current?.abort()
    controller.current = active
    const current = ++generation.current
    try {
      const result = await searchDocuments({ query, favorites_only: favorites, cursor: value.next_cursor, limit: 20 }, session.csrf_token, active.signal)
      if (!active.signal.aborted && current === generation.current) setValue((previous) => previous ? {
        ...result, items: [...previous.items, ...result.items.filter((item) => !previous.items.some((old) => old.id === item.id))],
      } : result)
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

  function arrows(event: KeyboardEvent<HTMLElement>) {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return
    const targets = Array.from(contentRef.current?.querySelectorAll<HTMLAnchorElement>('.search-results a') ?? [])
    if (!targets.length) return
    event.preventDefault()
    const index = targets.indexOf(document.activeElement as HTMLAnchorElement)
    targets[(index + (event.key === 'ArrowDown' ? 1 : targets.length - 1) + targets.length) % targets.length]?.focus()
  }

  const navigation = pages.filter((page) => page.name.toLowerCase().includes(query.trim().toLowerCase()))
  return <Dialog.Portal>
    <Dialog.Overlay className="global-search-overlay" />
    <Dialog.Content className="global-search-dialog" ref={contentRef} onKeyDown={arrows}>
      <div className="global-search-heading"><Dialog.Title>Find your way</Dialog.Title>
        <Dialog.Close aria-label="Close search"><X size={18} aria-hidden="true" /></Dialog.Close>
      </div>
      <Dialog.Description>Search review titles across your workspaces, or go to a page.</Dialog.Description>
      <label htmlFor="global-document-search">Search documents and pages</label>
      <div className="global-search-field"><Search size={18} aria-hidden="true" />
        <input id="global-document-search" type="search" autoComplete="off" maxLength={100}
          value={query} onChange={(event) => { clearResults(); setQuery(event.target.value) }} placeholder="Type a review title or page…" />
      </div>
      <button className="search-favorites" type="button" aria-pressed={favorites} onClick={() => { clearResults(); setFavorites((current) => !current) }}>
        <Star size={15} aria-hidden="true" /> Favorites only
      </button>
      <div className="search-results" aria-busy={pending}>
        {navigation.length > 0 && <section aria-label="Pages"><h2>Pages</h2><ul>{navigation.map((page) =>
          <li key={page.path}><Link to={page.path} onClick={onClose}><page.icon size={17} aria-hidden="true" />{page.name}</Link></li>,
        )}</ul></section>}
        <section aria-label="Matching documents"><h2>{query ? 'Matching documents' : 'Recent documents'}</h2>
          {value && <ul>{value.items.map((item) => <li key={item.id}>
            <Link to={`/documents/${item.id}/edit`} onClick={onClose}><FileText size={18} aria-hidden="true" />
              <span className="search-document-copy"><strong>{item.title || 'Untitled review'}</strong><small>{item.workspace_name}{!item.is_owner && ' · Assigned to you'}</small></span>
              {item.favorite && <Star size={15} aria-label="Favorite" />}{item.pinned && <Pin size={15} aria-label="Pinned" />}
            </Link></li>)}</ul>}
          {!pending && value?.items.length === 0 && <p>{value.next_cursor ? 'No matches in this group. Search more documents to continue.' : 'No matching reviews.'}</p>}
        </section>
      </div>
      {error && <div role="alert"><p>{error}</p><button type="button" onClick={() => { clearResults(); setAttempt((current) => current + 1) }}>Retry search</button></div>}
      <div className="global-search-footer"><span role="status">{pending ? 'Searching…' : `${value?.items.length ?? 0} review results`}</span>
        {value?.next_cursor && <button type="button" disabled={pending} onClick={() => void more()}>Search more documents</button>}
        <small>↑ ↓ to move · Enter to open · Esc to close</small>
      </div>
    </Dialog.Content>
  </Dialog.Portal>
}
