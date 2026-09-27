import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import {
  ApiConflictError, getDraft, saveDraftSource, type SessionView, type SourceView,
} from '../api/client'

type DraftState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; saved: SourceView }

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

export function EditDraftPage({ session }: { session: SessionView }) {
  const { documentId } = useParams<{ documentId: string }>()
  const [state, setState] = useState<DraftState>({ kind: 'loading' })
  const [text, setText] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)

  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    getDraft(documentId, controller.signal).then((saved) => {
      if (controller.signal.aborted) return
      setState({ kind: 'ready', saved })
      setText(saved.text)
      setError(null)
      setConflict(false)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setState({ kind: 'error', message: messageFrom(cause) })
    })
    return () => controller.abort()
  }, [documentId, attempt])

  const dirty = state.kind === 'ready' && text !== state.saved.text
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!documentId || state.kind !== 'ready' || !dirty) return
    setPending(true)
    setError(null)
    setNotice(null)
    try {
      const saved = await saveDraftSource(
        documentId, state.saved.version, text, session.csrf_token,
      )
      setState({
        kind: 'ready',
        saved: {
          ...state.saved,
          version: saved.version,
          text,
          status: saved.status,
          expires_at: saved.expires_at,
        },
      })
      setConflict(false)
      setNotice('Draft saved as a new source revision. Review it again before export.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) {
        setConflict(true)
        setError('This draft changed in another session. Copy your edits or reload the latest saved version.')
      } else {
        setError(messageFrom(cause))
      }
    } finally {
      setPending(false)
    }
  }

  async function copyUnsaved() {
    try {
      await navigator.clipboard.writeText(text)
      setNotice('Unsaved text copied. You can now reload the saved version.')
    } catch {
      setError('The browser could not copy your edits. Select the text and copy it manually.')
    }
  }

  function reloadSaved() {
    setPending(false)
    setError(null)
    setNotice(null)
    setConflict(false)
    setState({ kind: 'loading' })
    setAttempt((value) => value + 1)
  }

  return (
    <section>
      <h1>Saved draft</h1>
      {state.kind === 'loading' && <p role="status">Loading the saved draft…</p>}
      {state.kind === 'error' && (
        <div role="alert">
          <p>{state.message}</p>
          <button type="button" onClick={reloadSaved}>Retry</button>
        </div>
      )}
      {state.kind === 'ready' && (
        <>
          <p>{state.saved.title || `Review ${state.saved.version.document_id}`}</p>
          <p>Status: {state.saved.status}. Expires: {new Date(state.saved.expires_at).toLocaleString()}.</p>
          <p>Suggestions: {state.saved.categories.join(', ') || 'none'}; phone region: {state.saved.phone_region}.</p>
          <p>Source revision: {state.saved.version.source_revision_id}</p>
          {error && <p role="alert">{error}</p>}
          {notice && <p role="status">{notice}</p>}
          <form onSubmit={save}>
            <label htmlFor="saved-source">Text to review</label>
            <textarea id="saved-source" className="source-editor" value={text}
              onChange={(event) => {
                setText(event.target.value)
                setNotice(null)
              }} />
            <p role="status">
              {Array.from(text).length.toLocaleString()} characters.
              {' '}{dirty ? 'Unsaved edits.' : 'Saved.'}
            </p>
            <button type="submit" disabled={!dirty || pending || conflict}>
              {pending ? 'Saving…' : 'Save new revision'}
            </button>{' '}
            <button type="button" onClick={reloadSaved} disabled={pending}>
              {dirty ? 'Discard edits and reload saved' : 'Reload saved'}
            </button>
          </form>
          {conflict && (
            <button type="button" onClick={() => void copyUnsaved()}>
              Copy unsaved edits
            </button>
          )}
        </>
      )}
    </section>
  )
}
