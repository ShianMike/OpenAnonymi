import { useEffect, useRef, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { Link, useSearchParams } from 'react-router-dom'
import { Check, CircleAlert, FileSearch, Plus, X } from 'lucide-react'
import { ApiRequestError, deleteDocument, bulkDocuments, updateDocumentPreference,
  type DocumentPreferenceRequest, type BulkDocumentsRequest, type BulkDocumentsView,
  type DocumentIndexView, type SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { DocumentGallery } from './documents/DocumentGallery'
import { DocumentFilters } from './documents/DocumentFilters'
import { DocumentDeleteDialog } from './documents/DocumentDeleteDialog'
import { BulkDeleteDialog } from './documents/BulkDeleteDialog'
import { RetentionDialog } from '../retention/RetentionDialog'
import { DocumentBulkActions, DocumentBulkResults } from './documents/DocumentBulkActions'
import { ResumeReview } from './documents/ResumeReview'
import { currentDocuments, readDocumentQuery, visibleDocuments } from './documents/documentPresentation'
import { useDocuments } from './documents/useDocuments'
import { useLastReview } from '../resume/lastReview'
import { reviewQueue } from '../resume/reviewQueue'
import { rememberReviewWorkspace, useReviewWorkspace } from '../resume/reviewWorkspace'
import { ListPagination } from '../ui/ListPagination'
import { pageWindow } from '../ui/pagination'
import './documents/documents.css'

type Deletion = { item: DocumentIndexView; trigger: HTMLButtonElement | null }
type Renewal = Deletion & { workspaceId: string }

export function DocumentsPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const preferred = useReviewWorkspace(session.user_id)
  const membership = session.memberships.find(item => item.workspace_id === params.get('workspace'))
    ?? session.memberships.find(item => item.workspace_id === preferred) ?? session.memberships[0]
  const workspaceId = membership?.workspace_id ?? ''
  const query = readDocumentQuery(params)
  const [deleting, setDeleting] = useState(false)
  const [confirmation, setConfirmation] = useState<Deletion | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [selected, setSelected] = useState(new Set<string>())
  const [selecting, setSelecting] = useState(false)
  const [bulkPending, setBulkPending] = useState(false)
  const [bulkConfirm, setBulkConfirm] = useState(false)
  const [renewing, setRenewing] = useState<Renewal | null>(null)
  const [preferencePending, setPreferencePending] = useState(new Set<string>())
  const [bulkResults, setBulkResults] = useState<{ value: BulkDocumentsView; items: DocumentIndexView[] } | null>(null)
  const busy = bulkPending || deleting || preferencePending.size > 0 || renewing !== null
  const { data, retry, updateItems } = useDocuments(session.user_id, workspaceId, busy)
  const lastId = useLastReview(session.user_id, workspaceId)
  const currentWorkspace = useRef(workspaceId)
  const pageRef = useRef<HTMLElement>(null)
  const bulkTrigger = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (bulkResults) pageRef.current?.querySelector<HTMLElement>('.document-bulk-results summary')?.focus()
  }, [bulkResults])
  useEffect(() => {
    currentWorkspace.current = workspaceId
    return () => { currentWorkspace.current = '' }
  }, [workspaceId])
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (!workspaceId) return
    rememberReviewWorkspace(session.user_id, workspaceId)
    if (params.get('workspace') !== workspaceId) setParams(current => {
      const next = new URLSearchParams(current); next.set('workspace', workspaceId); return next
    }, { replace: true })
  }, [session.user_id, workspaceId, params, setParams])

  const items = data.kind === 'ready' ? currentDocuments(data.items, now) : []
  const visible = visibleDocuments(items, query)
  const range = pageWindow(visible.length, query.page, 25)
  const pageItems = visible.slice(range.start, range.end)
  const selection = new Set([...selected].filter(id => items.some(item => item.id === id)))
  const allSelected = pageItems.length > 0 && pageItems.every(item => selection.has(item.id))
  const queue = reviewQueue(items, lastId, now)
  const filtered = query.search.length > 0 || query.status !== 'all'
  const listSearch = params.toString()
  const newReview = `/new?workspace=${encodeURIComponent(workspaceId)}`

  function endSelection() {
    if (busy) return
    setSelecting(false)
    setSelected(new Set())
    requestAnimationFrame(() => pageRef.current?.querySelector<HTMLButtonElement>('#document-select-mode')?.focus({ preventScroll: true }))
  }
  function changeQuery(name: string, value: string) {
    setSelected(new Set())
    setBulkResults(null)
    const next = new URLSearchParams(window.location.search)
    const defaultValue = name === 'view' || name === 'status' ? 'all' : name === 'sort' ? 'updated' : name === 'page' ? '0' : ''
    if (value && value !== defaultValue) next.set(name, value)
    else next.delete(name)
    if (name !== 'page') next.delete('page')
    if (name === 'view') next.delete('status')
    setParams(next, { replace: name === 'q' })
  }
  function clearFilters() {
    setSelected(new Set())
    const next = new URLSearchParams(window.location.search)
    for (const name of ['q', 'status', 'page']) next.delete(name)
    setParams(next)
  }

  async function preference(item: DocumentIndexView, value: DocumentPreferenceRequest) {
    if (preferencePending.has(item.id) || bulkPending) return
    const scope = workspaceId
    setPreferencePending(current => new Set(current).add(item.id))
    setActionError(null)
    try {
      const result = await updateDocumentPreference(item.id, value, session.csrf_token)
      if (currentWorkspace.current !== scope) return
      updateItems(current => current.map(row => row.id === item.id ? { ...row, favorite: result.favorite, pinned: result.pinned } : row))
      if (query.view === 'favorites' && !result.favorite) requestAnimationFrame(() => pageRef.current?.querySelector<HTMLInputElement>('#document-search')?.focus())
    } catch (cause) {
      if (currentWorkspace.current !== scope) return
      if (cause instanceof ApiRequestError && [404, 410].includes(cause.status)) {
        updateItems(current => current.filter(row => row.id !== item.id || cause.status !== 404)
          .map(row => row.id === item.id ? { ...row, title: null, status: 'expired', favorite: false, pinned: false } : row))
      }
      setActionError(cause instanceof Error ? cause.message : 'Preferences could not be saved.')
    } finally {
      setPreferencePending(current => { const next = new Set(current); next.delete(item.id); return next })
    }
  }

  async function applyBulk(action: BulkDocumentsRequest['action']) {
    if (busy || !selection.size || data.kind !== 'ready') return
    const scope = workspaceId
    const affected = items.filter(item => selection.has(item.id))
    setBulkPending(true); setActionError(null); setBulkResults(null)
    try {
      const result = await bulkDocuments(scope, { document_ids: affected.map(item => item.id), action }, session.csrf_token)
      if (currentWorkspace.current !== scope) return
      const outcomes = new Map(result.outcomes.map(item => [item.document_id, item]))
      updateItems(current => current.filter(row => !['deleted', 'not_found'].includes(outcomes.get(row.id)?.outcome ?? ''))
        .map(row => { const change = outcomes.get(row.id); return change?.outcome === 'updated' ? { ...row, favorite: change.favorite ?? row.favorite, pinned: change.pinned ?? row.pinned } : change?.outcome === 'unavailable' ? { ...row, title: null, status: 'expired', favorite: false, pinned: false } : row }))
      setSelected(new Set())
      setSelecting(false)
      setBulkResults({ value: result, items: affected.map(item => ['not_found', 'unavailable', 'deleted'].includes(outcomes.get(item.id)?.outcome ?? '') ? { ...item, title: null, status: 'expired' } : item) })
    } catch (cause) {
      if (currentWorkspace.current === scope) {
        setActionError(cause instanceof Error ? cause.message : 'The action could not be completed. Refresh documents to check the current state.')
        requestAnimationFrame(() => bulkTrigger.current?.focus())
      }
    } finally { setBulkPending(false); setBulkConfirm(false) }
  }

  async function removeDocument() {
    if (!confirmation || deleting) return
    const scope = workspaceId
    setDeleting(true); setActionError(null); setNotice(null)
    try {
      await deleteDocument(confirmation.item.id, session.csrf_token)
      if (currentWorkspace.current !== scope) return
      updateItems(current => current.filter(row => row.id !== confirmation.item.id))
      setConfirmation(null)
      setNotice('Review deleted. Its stored content is scheduled for removal.')
      requestAnimationFrame(() => pageRef.current?.querySelector<HTMLInputElement>('#document-search')?.focus())
    } catch (cause) {
      if (currentWorkspace.current === scope) setActionError(cause instanceof Error ? cause.message : 'Review could not be deleted.')
    } finally { setDeleting(false) }
  }
  function cancelDeletion() {
    if (deleting) return
    const trigger = confirmation?.trigger
    setConfirmation(null); setActionError(null)
    requestAnimationFrame(() => trigger?.focus())
  }

  return <section ref={pageRef} className="documents-page" aria-labelledby="documents-title" onKeyDown={event => {
    if (event.key === 'Escape' && selecting && !busy && !bulkConfirm && !confirmation && !event.defaultPrevented &&
      !(event.target as Element).closest('[role="menu"], [role="listbox"]')) {
      event.preventDefault()
      endSelection()
    }
  }}>
    <header className="documents-heading">
      <div><h1 id="documents-title">Documents</h1><p>Everything you’re reviewing, in one place.</p></div>
      <Link className="document-create" to={newReview} aria-disabled={!membership} onClick={event => { if (!membership) event.preventDefault() }}><Plus size={16} aria-hidden="true" />New review</Link>
    </header>
    {!membership ? <div className="document-empty" role="status"><h2>No active workspace</h2><p>You need a workspace membership to view documents.</p></div> : <>
      {data.kind === 'ready' && queue.last && query.view === 'all' && !filtered && <ResumeReview item={queue.last} search={listSearch} />}
      {data.kind === 'ready' && data.unavailable && <p className="document-access-note" role="status">Your last review is no longer available. Choose another document below.</p>}
      <Tabs.Root value={query.view} onValueChange={value => changeQuery('view', value)} className="document-library">
        <DocumentFilters items={data.kind === 'ready' ? items : undefined} query={query} refreshing={data.kind === 'ready' && data.refreshing} disabled={busy || data.kind === 'loading'} onChange={changeQuery} onRefresh={retry}
          selecting={selecting} canSelect={pageItems.length > 0} onToggleSelection={() => {
            if (selecting) endSelection()
            else {
              setSelecting(true); setBulkResults(null)
              requestAnimationFrame(() => pageRef.current?.querySelector<HTMLInputElement>('.document-card-selector')?.focus({ preventScroll: true }))
            }
          }} />
        <Tabs.Content value={query.view} className="document-view-content">
          {data.kind === 'loading' && <LoadingState label="Loading your documents…" description="Checking your available reviews and shared work." shape="gallery" onRetry={retry} />}
          {data.kind === 'error' && <div className="document-empty document-load-error" role="alert"><CircleAlert size={26} aria-hidden="true" /><h2>Documents couldn’t be loaded</h2><p>{data.message}</p><button type="button" onClick={retry}>Try again</button></div>}
          {data.kind === 'ready' && <>
            {(selecting || (filtered && visible.length > 0)) && <div className="document-list-summary" data-selecting={selecting || undefined} role={selecting ? 'region' : undefined} aria-label={selecting ? 'Document selection' : undefined}>
              {selecting ? <>
                <span className="document-selection-count" role="status">{selection.size} selected</span>
                <span id="document-selection-help" className="document-selection-help">Choose cards. Esc to exit.</span>
                <div className="document-selection-controls">
                  {pageItems.length > 0 && <button type="button" disabled={busy} className="document-selection-page" onClick={() => setSelected(allSelected ? new Set() : new Set(pageItems.map(item => item.id)))}>{allSelected ? 'Clear' : 'Select page'}</button>}
                  {selection.size > 0 && !allSelected && <button type="button" disabled={busy} className="document-selection-page" onClick={() => setSelected(new Set())}>Clear</button>}
                  <DocumentBulkActions count={selection.size} pending={busy} canDelete={items.some(item => item.is_owner && selection.has(item.id))}
                    canUpdate={items.some(item => item.status !== 'expired' && selection.has(item.id))}
                    onApply={(action, trigger) => { bulkTrigger.current = trigger; if (action === 'delete') setBulkConfirm(true); else void applyBulk(action) }} />
                  <button type="button" className="document-icon-button" disabled={busy} aria-label="Exit selection mode" title="Exit selection mode" onClick={endSelection}><X size={16} /></button>
                </div>
              </> : <button type="button" className="document-clear-filters" onClick={clearFilters}>Clear filters<X size={13} aria-hidden="true" /></button>}
            </div>}
            {actionError && !confirmation && <p className="document-action-error" role="alert">{actionError}</p>}
            {bulkResults && <DocumentBulkResults results={bulkResults} onDismiss={() => { setBulkResults(null); pageRef.current?.querySelector<HTMLButtonElement>('#document-select-mode')?.focus() }} />}
            {visible.length === 0 ? <div className="document-empty">
              <FileSearch size={28} strokeWidth={1.3} aria-hidden="true" />
              <h2>{filtered ? 'No matching documents' : query.view === 'shared' ? 'Nothing shared with you yet' : query.view === 'in_progress' ? 'You’re all caught up' : query.view === 'favorites' ? 'Keep your go-to documents here' : query.view === 'completed' ? 'No completed reviews yet' : 'Your first review starts here'}</h2>
              <p>{filtered ? 'Try a different title or review status.' : query.view === 'shared' ? 'When a teammate assigns you a review, you’ll find it here.' : query.view === 'favorites' ? 'Use a document’s actions menu to add it to your favorites.' : query.view === 'completed' ? 'Reviews appear here after you confirm their output.' : 'Create a review to choose what stays private before you share.'}</p>
              {filtered ? <button type="button" onClick={clearFilters}>Clear filters</button> : query.view === 'in_progress' || (query.view === 'all' && !items.length) ? <Link to={newReview} className="document-create"><Plus size={15} aria-hidden="true" />New review</Link> : <button type="button" onClick={() => changeQuery('view', 'all')}>View all documents</button>}
            </div> : <>
              <DocumentGallery items={pageItems} workspaceId={workspaceId} search={listSearch} now={now} selected={selection} selecting={selecting} pending={busy} preferencePending={preferencePending}
                onDelete={(item, trigger) => { setActionError(null); setConfirmation({ item, trigger }) }}
                onSelect={(id, value) => setSelected(current => { const next = new Set(current); if (value && next.size < 50) next.add(id); else next.delete(id); return next })}
                onPreference={(item, value) => void preference(item, value)} onRenew={(item, trigger) => setRenewing({ item, trigger, workspaceId })} />
              <ListPagination page={range.page} total={visible.length} pageSize={25} label="Documents" pending={busy}
                onPrevious={() => changeQuery('page', String(range.page - 1))} onNext={() => changeQuery('page', String(range.page + 1))} />
            </>}
          </>}
        </Tabs.Content>
      </Tabs.Root>
    </>}
    {notice && <div className="document-feedback" role="status"><Check size={16} aria-hidden="true" /><span>{notice}</span><button type="button" className="document-icon-button" aria-label="Dismiss notification" onClick={() => setNotice(null)}><X size={15} /></button></div>}
    {confirmation && <DocumentDeleteDialog item={confirmation.item} pending={deleting} error={actionError} onCancel={cancelDeletion} onConfirm={() => void removeDocument()} />}
    {bulkConfirm && <BulkDeleteDialog count={selection.size} pending={bulkPending} onCancel={() => { setBulkConfirm(false); requestAnimationFrame(() => bulkTrigger.current?.focus()) }} onConfirm={() => void applyBulk('delete')} />}
    {renewing && <RetentionDialog key={`${renewing.item.id}.${session.csrf_token}`} documentId={renewing.item.id} csrf={session.csrf_token} returnFocus={renewing.trigger}
      onClose={() => setRenewing(null)} onSaved={value => {
        if (currentWorkspace.current !== renewing.workspaceId) return
        updateItems(current => current.map(item => item.id === renewing.item.id ? { ...item, expires_at: value.expires_at } : item))
        setNotice('Retention renewed. Your source and review decisions are preserved.'); setRenewing(null)
      }} />}
  </section>
}
