import { LoadingState } from '../loading/LoadingState'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2, FileSearch, Plus } from 'lucide-react'
import {
  ApiRequestError,
  deleteDocument,
  bulkDocuments,
  updateDocumentPreference,
  type DocumentPreferenceRequest,
  type BulkDocumentsRequest,
  type BulkDocumentsView,
  getWorkspaceDocuments,
  type DocumentIndexView,
  type SessionView,
} from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { DocumentTable } from './documents/DocumentTable'
import { DocumentFilters } from './documents/DocumentFilters'
import { DocumentDeleteDialog } from './documents/DocumentDeleteDialog'
import { BulkDeleteDialog } from './documents/BulkDeleteDialog'
import { RetentionDialog } from '../retention/RetentionDialog'
import { DocumentBulkActions } from './documents/DocumentBulkActions'
import { documentLabel, matchesStatus, type DocumentSort } from './documents/documentPresentation'
import './documents/documents.css'

type Data =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; items: DocumentIndexView[] }
type Deletion = { item: DocumentIndexView; trigger: HTMLButtonElement | null }
type Renewal = Deletion & { workspaceId: string }

export function DocumentsPage({ session }: { session: SessionView }) {
  const [params] = useSearchParams()
  const [workspaceId, setWorkspaceId] = useState(() => session.memberships.find((item) => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState<DocumentSort>('newest')
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [confirmation, setConfirmation] = useState<Deletion | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [selected, setSelected] = useState(new Set<string>())
  const [bulkAction, setBulkAction] = useState<BulkDocumentsRequest['action']>('favorite')
  const [bulkPending, setBulkPending] = useState(false)
  const [bulkConfirm, setBulkConfirm] = useState(false)
  const [renewing, setRenewing] = useState<Renewal | null>(null)
  const [preferencePending, setPreferencePending] = useState(new Set<string>())
  const [bulkResults, setBulkResults] = useState<{ value: BulkDocumentsView; items: DocumentIndexView[] } | null>(null)
  const currentWorkspace = useRef(workspaceId)
  const pageRef = useRef<HTMLElement>(null)
  const noticeRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (notice) noticeRef.current?.focus()
  }, [notice])

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspaceDocuments(workspaceId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setData({ kind: 'ready', items })
          setSelected((current) => new Set([...current].filter((id) => items.some((item) => item.id === id))))
          setRefreshError(null)
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        const message = cause instanceof Error ? cause.message : 'Documents could not be loaded.'
        if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) {
          setData({ kind: 'error', message })
          setSelected(new Set())
          setBulkResults(null)
          return
        }
        setRefreshError(message)
        setData((current) => (current.kind === 'ready' ? current : { kind: 'error', message }))
      })
      .finally(() => {
        if (!controller.signal.aborted) setRefreshing(false)
      })
    return () => controller.abort()
  }, [workspaceId, attempt])

  const visible =
    data.kind === 'ready'
      ? data.items
          .filter(
            (item) =>
              matchesStatus(item, status) &&
              (!search.trim() ||
                documentLabel(item).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),
          )
          .sort((left, right) => {
            if (left.pinned !== right.pinned) return left.pinned ? -1 : 1
            if (sort === 'title') return documentLabel(left).localeCompare(documentLabel(right))
            if (sort === 'expiring') return left.expires_at.localeCompare(right.expires_at)
            if (sort === 'oldest') return left.created_at.localeCompare(right.created_at)
            return right.created_at.localeCompare(left.created_at)
          })
      : []

  async function preference(item: DocumentIndexView, value: DocumentPreferenceRequest) {
    if (preferencePending.has(item.id) || bulkPending) return
    const scope = workspaceId
    setPreferencePending((current) => new Set(current).add(item.id))
    setActionError(null)
    try {
      const result = await updateDocumentPreference(item.id, value, session.csrf_token)
      if (currentWorkspace.current !== scope) return
      setData((current) => current.kind === 'ready' ? { kind: 'ready', items: current.items.map((row) => row.id === item.id ? { ...row, favorite: result.favorite, pinned: result.pinned } : row) } : current)
    } catch (cause) {
      if (currentWorkspace.current === scope && cause instanceof ApiRequestError && [404, 410].includes(cause.status)) {
        setData((current) => current.kind === 'ready' ? { kind: 'ready', items: current.items
          .filter((row) => row.id !== item.id || cause.status !== 404)
          .map((row) => row.id === item.id ? { ...row, title: null, status: 'expired', favorite: false, pinned: false } : row) } : current)
        setAttempt((current) => current + 1)
      }
      if (currentWorkspace.current === scope) setActionError(cause instanceof Error ? cause.message : 'Preferences could not be saved.')
    } finally {
      setPreferencePending((current) => { const next = new Set(current); next.delete(item.id); return next })
    }
  }

  async function applyBulk() {
    if (bulkPending || !selected.size || data.kind !== 'ready') return
    const scope = workspaceId
    const items = data.items.filter((item) => selected.has(item.id))
    setBulkPending(true)
    setActionError(null)
    setBulkResults(null)
    try {
      const result = await bulkDocuments(scope, { document_ids: items.map((item) => item.id), action: bulkAction }, session.csrf_token)
      if (currentWorkspace.current !== scope) return
      const outcomes = new Map(result.outcomes.map((item) => [item.document_id, item]))
      setData((current) => current.kind === 'ready' ? { kind: 'ready', items: current.items
        .filter((row) => !['deleted', 'not_found'].includes(outcomes.get(row.id)?.outcome ?? ''))
        .map((row) => { const change = outcomes.get(row.id); return change?.outcome === 'updated' ? { ...row, favorite: change.favorite ?? row.favorite, pinned: change.pinned ?? row.pinned } : change?.outcome === 'unavailable' ? { ...row, title: null, status: 'expired', favorite: false, pinned: false } : row }) } : current)
      setSelected(new Set(result.outcomes.filter((item) => item.outcome === 'unavailable').map((item) => item.document_id)))
      setBulkResults({ value: result, items: items.map((item) => ['not_found', 'unavailable'].includes(outcomes.get(item.id)?.outcome ?? '') ? { ...item, title: null, status: 'expired' } : item) })
      setRefreshing(true)
      setAttempt((current) => current + 1)
    } catch (cause) {
      if (currentWorkspace.current === scope) setActionError(cause instanceof Error ? cause.message : 'The bulk action could not be completed. Refresh documents to check their current state.')
    } finally { setBulkPending(false); setBulkConfirm(false) }
  }

  async function removeDocument() {
    if (!confirmation || deleting) return
    setDeleting(true)
    setActionError(null)
    setNotice(null)
    try {
      await deleteDocument(confirmation.item.id, session.csrf_token)
      setData((current) =>
        current.kind === 'ready'
          ? { kind: 'ready', items: current.items.filter((row) => row.id !== confirmation.item.id) }
          : current,
      )
      setConfirmation(null)
      setNotice('Review deleted. Its stored content is scheduled for removal.')
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : 'Review could not be deleted.')
    } finally {
      setDeleting(false)
    }
  }

  function cancelDeletion() {
    if (deleting) return
    const trigger = confirmation?.trigger
    setConfirmation(null)
    setActionError(null)
    requestAnimationFrame(() => trigger?.focus())
  }

  return (
    <section ref={pageRef} className="documents-page" aria-labelledby="documents-title">
      <header className="documents-heading">
        <div>
          <h1 id="documents-title">Documents</h1>
          <p>Find a review, pick up where you left off, and share when you’re ready.</p>
        </div>
        <div className="documents-heading-tools">
          {session.memberships.length > 1 && (
            <div className="workspace-picker">
              <label htmlFor="documents-workspace">Workspace</label>
              <GlassSelect
                id="documents-workspace"
                value={workspaceId}
                disabled={bulkPending || deleting || preferencePending.size > 0 || renewing !== null}
                onValueChange={(value) => {
                  setWorkspaceId(value)
                  currentWorkspace.current = value
                  setData({ kind: 'loading' })
                  setRefreshError(null)
                  setSelected(new Set())
                  setBulkResults(null)
                  setActionError(null)
                }}
              >
                {session.memberships.map((membership, index) => (
                  <option key={membership.workspace_id} value={membership.workspace_id}>
                    {membership.workspace_name || `Workspace ${index + 1}`}
                  </option>
                ))}
              </GlassSelect>
            </div>
          )}
          <Link className="button-primary" to={`/new?workspace=${encodeURIComponent(workspaceId)}`}>
            <Plus size={17} aria-hidden="true" /> New review
          </Link>
        </div>
      </header>
      {notice && (
        <p className="document-notice" role="status" ref={noticeRef} tabIndex={-1}>
          <CheckCircle2 size={17} aria-hidden="true" />
          {notice}
        </p>
      )}
      {data.kind === 'loading' && <LoadingState label="Loading documents…" description="Finding the reviews available in this workspace." />}
      {data.kind === 'error' && (
        <div role="alert">
          <p>{data.message}</p>
          <button
            type="button"
            onClick={() => {
              setData({ kind: 'loading' })
              setAttempt((value) => value + 1)
            }}
          >
            Retry documents
          </button>
        </div>
      )}
      {data.kind === 'ready' && (
        <div className="document-collection">
          <DocumentFilters
            items={data.items}
            visibleCount={visible.length}
            search={search}
            status={status}
            sort={sort}
            refreshing={refreshing}
            pageRef={pageRef}
            onSearch={(value) => { setSearch(value); setSelected(new Set()) }}
            onStatus={(value) => { setStatus(value); setSelected(new Set()) }}
            onSort={setSort}
            onRefresh={() => {
              setRefreshing(true)
              setAttempt((value) => value + 1)
            }}
          />
          {actionError && !confirmation && <p className="document-refresh-error" role="alert">{actionError}</p>}
          <DocumentBulkActions count={selected.size} action={bulkAction} pending={bulkPending || deleting || preferencePending.size > 0}
            onAction={setBulkAction} onApply={() => { if (bulkAction === 'delete') setBulkConfirm(true); else void applyBulk() }}
            onClear={() => {
              setSelected(new Set())
              pageRef.current?.querySelector<HTMLInputElement>('#document-select-visible')?.focus()
            }} results={bulkResults} />
          {refreshError && (
            <p className="document-refresh-error" role="alert">
              {refreshError} Your last loaded list is still shown.
            </p>
          )}
          {visible.length === 0 ? (
            <div className="document-empty">
              <span className="document-empty-icon">
                <FileSearch size={27} strokeWidth={1.3} aria-hidden="true" />
              </span>
              <h2>{data.items.length === 0 ? 'Your reviews start here' : 'No documents found'}</h2>
              <p>
                {data.items.length === 0
                  ? 'Add some text to create your first review.'
                  : 'Try a different title or adjust your filters.'}
              </p>
              {data.items.length === 0 ? (
                <Link className="button-primary" to={`/new?workspace=${encodeURIComponent(workspaceId)}`}>
                  Create a review
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setSearch('')
                    setStatus('all')
                  }}
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <DocumentTable
              items={visible}
              workspaceId={workspaceId}
              now={now}
              onDelete={(item, trigger) => {
                setActionError(null)
                setConfirmation({ item, trigger })
              }}
              selected={selected} pending={bulkPending || deleting} preferencePending={preferencePending}
              onSelectVisible={(value) => setSelected(value ? new Set(visible.slice(0, 50).map((item) => item.id)) : new Set())}
              onSelect={(id, value) => setSelected((current) => { const next = new Set(current); if (value && next.size < 50) next.add(id); else next.delete(id); return next })}
              onPreference={(item, value) => void preference(item, value)}
              onRenew={(item, trigger) => setRenewing({ item, trigger, workspaceId })}
            />
          )}
        </div>
      )}
      {confirmation && (
        <DocumentDeleteDialog
          item={confirmation.item}
          pending={deleting}
          error={actionError}
          onCancel={cancelDeletion}
          onConfirm={() => void removeDocument()}
        />
      )}
      {bulkConfirm && <BulkDeleteDialog count={selected.size} pending={bulkPending} onCancel={() => setBulkConfirm(false)} onConfirm={() => void applyBulk()} />}
      {renewing && <RetentionDialog key={`${renewing.item.id}.${session.csrf_token}`} documentId={renewing.item.id} csrf={session.csrf_token} returnFocus={renewing.trigger}
        onClose={() => setRenewing(null)} onSaved={value => {
          if (currentWorkspace.current !== renewing.workspaceId) return
          setData(current => current.kind === 'ready' ? { kind: 'ready', items: current.items.map(item => item.id === renewing.item.id ? { ...item, expires_at: value.expires_at } : item) } : current)
          setNotice('Retention renewed. Your source and review decisions are preserved.'); setRenewing(null)
        }} />}
    </section>
  )
}
