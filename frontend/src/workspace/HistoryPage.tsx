import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDocumentHistory, type DocumentHistoryView } from '../api/client'
import { eventName } from './events'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; value: DocumentHistoryView }

export function HistoryPage() {
  const { workspaceId, documentId } = useParams<{ workspaceId: string; documentId: string }>()
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!workspaceId || !documentId) return
    const controller = new AbortController()
    getDocumentHistory(workspaceId, documentId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', value })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({
        kind: 'error', message: cause instanceof Error ? cause.message : 'History could not be loaded.',
      })
    })
    return () => controller.abort()
  }, [workspaceId, documentId, attempt])

  if (!workspaceId || !documentId) {
    return <section><h1>Review history</h1><p role="alert">Review not found.</p></section>
  }

  return (
    <section aria-labelledby="history-title">
      <h1 id="history-title">Review history</h1>
      <p><Link to="/documents">Back to documents</Link></p>
      {data.kind === 'loading' && <p role="status">Loading review history…</p>}
      {data.kind === 'error' && (
        <div role="alert"><p>{data.message}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry history</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <p>Status: {data.value.status.replaceAll('_', ' ')}. Created {' '}
            {new Date(data.value.created_at).toLocaleString()}; content expires {' '}
            {new Date(data.value.expires_at).toLocaleString()}.</p>
          {data.value.deleted_at && <p>Deleted {new Date(data.value.deleted_at).toLocaleString()}.</p>}
          {data.value.status !== 'deleted' && data.value.status !== 'expired' && (
            <p><Link to={`/documents/${data.value.document_id}/edit`}>Open current review</Link></p>
          )}
          <h2>Source revisions</h2>
          <p>Showing {data.value.revisions.length} of {data.value.revision_total} revision(s).
            Earlier source text cannot be reopened from this history.</p>
          {data.value.revisions.length === 0 ? <p>No source revisions remain.</p> : (
            <ol>{data.value.revisions.map((revision) => (
              <li key={revision.number}>Revision {revision.number}; {' '}
                {new Date(revision.created_at).toLocaleString()}
                {revision.is_current ? '; current' : ''}</li>
            ))}</ol>
          )}
          <h2>Actions</h2>
          <p>Showing the latest {data.value.events.length} of {data.value.event_total} retained event(s).
            This history contains no original text or replacement mapping.</p>
          {data.value.events.length === 0 ? <p>No retained actions.</p> : (
            <ol>{data.value.events.map((event, index) => (
              <li key={`${event.occurred_at}-${index}`}>
                {eventName(event.event_code)} — {event.outcome}; {' '}
                {new Date(event.occurred_at).toLocaleString()}
              </li>
            ))}</ol>
          )}
        </>
      )}
    </section>
  )
}
