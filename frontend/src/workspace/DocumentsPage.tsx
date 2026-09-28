import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  deleteDocument, getWorkspaceDocuments, type DocumentIndexView, type SessionView,
} from '../api/client'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; items: DocumentIndexView[] }
type Sort = 'newest' | 'oldest' | 'expiring' | 'title'

export function DocumentsPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState<Sort>('newest')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspaceDocuments(workspaceId, controller.signal).then((items) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', items })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({
        kind: 'error',
        message: cause instanceof Error ? cause.message : 'Documents could not be loaded.',
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  const visible = data.kind === 'ready' ? data.items.filter((item) =>
    (status === 'all' || item.status === status) &&
    (!search.trim() || (item.title || `Review ${item.id}`)
      .toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),
  ).sort((left, right) => {
    if (sort === 'title') {
      return (left.title || `Review ${left.id}`).localeCompare(right.title || `Review ${right.id}`)
    }
    if (sort === 'expiring') return left.expires_at.localeCompare(right.expires_at)
    if (sort === 'oldest') return left.created_at.localeCompare(right.created_at)
    return right.created_at.localeCompare(left.created_at)
  }) : []

  async function removeDocument(item: DocumentIndexView) {
    if (!window.confirm(
      `Delete ${item.title || `Review ${item.id}`}? This ends access immediately and schedules its stored content for permanent removal. It cannot be restored.`,
    )) return
    setDeletingId(item.id)
    setActionError(null)
    setNotice(null)
    try {
      await deleteDocument(item.id, session.csrf_token)
      setData((current) => current.kind === 'ready'
        ? { kind: 'ready', items: current.items.filter((row) => row.id !== item.id) }
        : current)
      setNotice('Review deleted. Its stored content is scheduled for removal.')
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : 'Review could not be deleted.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section aria-labelledby="documents-title">
      <h1 id="documents-title">Documents</h1>
      <p>Your saved reviews in this workspace. Expired content cannot be reopened.</p>
      {actionError && <p role="alert">{actionError}</p>}
      {notice && <p role="status">{notice}</p>}
      {session.memberships.length > 1 && (
        <>
          <label htmlFor="documents-workspace">Workspace</label>{' '}
          <select id="documents-workspace" value={workspaceId} onChange={(event) => {
            setWorkspaceId(event.target.value)
            setData({ kind: 'loading' })
          }}>
            {session.memberships.map((membership, index) => (
              <option key={membership.workspace_id} value={membership.workspace_id}>
                Workspace {index + 1}
              </option>
            ))}
          </select>
        </>
      )}
      {data.kind === 'loading' && <p role="status">Loading documents…</p>}
      {data.kind === 'error' && (
        <div role="alert">
          <p>{data.message}</p>
          <button type="button" onClick={() => {
            setData({ kind: 'loading' })
            setAttempt((value) => value + 1)
          }}>Retry documents</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <div>
            <label htmlFor="document-search">Search titles</label>{' '}
            <input id="document-search" type="search" value={search}
              onChange={(event) => setSearch(event.target.value)} />{' '}
            <label htmlFor="document-status">Status</label>{' '}
            <select id="document-status" value={status}
              onChange={(event) => setStatus(event.target.value)}>
              <option value="all">All statuses</option>
              {['draft', 'scanning', 'needs_review', 'ready', 'exported', 'failed', 'expired']
                .map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
            </select>{' '}
            <label htmlFor="document-sort">Sort</label>{' '}
            <select id="document-sort" value={sort}
              onChange={(event) => setSort(event.target.value as Sort)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="expiring">Expiring first</option>
              <option value="title">Title</option>
            </select>{' '}
            <button type="button" onClick={() => {
              setData({ kind: 'loading' })
              setAttempt((value) => value + 1)
            }}>Refresh</button>
          </div>
          <p role="status">Showing {visible.length} of {data.items.length} documents.</p>
          {visible.length === 0 ? <p>No documents match these filters.</p> : (
            <table>
              <thead><tr>
                <th scope="col">Document</th><th scope="col">Status</th>
                <th scope="col">Review progress</th><th scope="col">Created</th>
                <th scope="col">Updated</th><th scope="col">Expires</th>
                <th scope="col">Action</th>
              </tr></thead>
              <tbody>{visible.map((item) => (
                <tr key={item.id}>
                  <th scope="row">{item.title || `Review ${item.id}`}</th>
                  <td>{item.status.replaceAll('_', ' ')}</td>
                  <td>{item.decided_count} of {item.finding_count} findings decided</td>
                  <td>{new Date(item.created_at).toLocaleString()}</td>
                  <td>{new Date(item.updated_at).toLocaleString()}</td>
                  <td>{new Date(item.expires_at).toLocaleString()}</td>
                  <td>{item.status === 'expired' || item.status === 'deleted' ?
                    'Unavailable' : <Link to={`/documents/${item.id}/edit`}>Open review</Link>}{' '}
                    <button type="button" onClick={() => void removeDocument(item)}
                      disabled={deletingId !== null}>
                      {deletingId === item.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </>
      )}
    </section>
  )
}
