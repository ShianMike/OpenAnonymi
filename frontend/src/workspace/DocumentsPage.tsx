import { LoadingState } from '../loading/LoadingState'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2, FileSearch, Plus } from 'lucide-react'
import {
  deleteDocument,
  getWorkspaceDocuments,
  type DocumentIndexView,
  type SessionView,
} from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { GlassSelect } from '../ui/GlassSelect'
import { DocumentTable } from './documents/DocumentTable'
import { DocumentFilters } from './documents/DocumentFilters'
import { DocumentDeleteDialog } from './documents/DocumentDeleteDialog'
import { documentLabel, matchesStatus, type DocumentSort } from './documents/documentPresentation'
import './documents/documents.css'

type Data =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; items: DocumentIndexView[] }
type Deletion = { item: DocumentIndexView; trigger: HTMLButtonElement | null }

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
          setRefreshError(null)
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        const message = cause instanceof Error ? cause.message : 'Documents could not be loaded.'
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
            if (sort === 'title') return documentLabel(left).localeCompare(documentLabel(right))
            if (sort === 'expiring') return left.expires_at.localeCompare(right.expires_at)
            if (sort === 'oldest') return left.created_at.localeCompare(right.created_at)
            return right.created_at.localeCompare(left.created_at)
          })
      : []

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
      <PageHeader
        title="Documents"
        titleId="documents-title"
        description="A little care in every document. Pick up where you left off."
        action={
          <div className="batch-entry-actions"><Link to={`/batches?workspace=${encodeURIComponent(workspaceId)}`}>Batch reviews</Link>
          <Link className="button-primary" to="/new">
            <Plus size={17} aria-hidden="true" /> New review
          </Link>
          </div>
        }
      />
      {notice && (
        <p className="document-notice" role="status" ref={noticeRef} tabIndex={-1}>
          <CheckCircle2 size={17} aria-hidden="true" />
          {notice}
        </p>
      )}
      {session.memberships.length > 1 && (
        <div className="workspace-picker">
          <label htmlFor="documents-workspace">Workspace</label>
          <GlassSelect
            id="documents-workspace"
            value={workspaceId}
            onValueChange={(value) => {
              setWorkspaceId(value)
              setData({ kind: 'loading' })
              setRefreshError(null)
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
            onSearch={setSearch}
            onStatus={setStatus}
            onSort={setSort}
            onRefresh={() => {
              setRefreshing(true)
              setAttempt((value) => value + 1)
            }}
          />
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
                <Link className="button-primary" to="/new">
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
            />
          )}
          {visible.length > 0 && (
            <footer className="document-list-footer">
              <span>
                {visible.length} document{visible.length === 1 ? '' : 's'}
              </span>
              <span>Content is kept until its retention date.</span>
            </footer>
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
    </section>
  )
}
