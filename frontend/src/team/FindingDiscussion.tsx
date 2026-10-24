import { useEffect, useRef, useState } from 'react'
import { MessageSquare, Trash2 } from 'lucide-react'
import type { SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { StudioSelect } from '../review/studio/StudioControls'
import { categoryPresentation } from '../rules/categoryPresentation'
import { GlassTextarea } from '../ui/GlassTextarea'
import { InlineNotice } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { getComments, postComment, removeComment, type CommentView } from './api'

export type CommentDraft = { text: string; id: string }

export function FindingDiscussion({ review, session, active, busy, onBusyChange, finding, onFindingChange, drafts, onDraftChange }: {
  review: ReviewController; session: SessionView; active: boolean; busy: boolean; onBusyChange: (busy: boolean) => void
  drafts: Record<string, CommentDraft>; onDraftChange: (finding: string, text: string) => void
  finding: string; onFindingChange: (finding: string) => void
}) {
  const [rows, setRows] = useState<CommentView[] | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [removing, setRemoving] = useState<string | null>(null)
  const [operation, setOperation] = useState<'post' | 'delete' | null>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const selected = review.activeFindings.find(item => item.finding_id === finding)
  const validFinding = selected?.finding_id ?? ''
  const documentId = saved?.version.document_id
  const draft = drafts[validFinding]
  const text = draft?.text ?? ''
  useEffect(() => {
    if (!active || !documentId || !validFinding) return
    const controller = new AbortController()
    getComments(documentId, validFinding, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setRows(value); setError('') } })
      .catch(cause => { if (!controller.signal.aborted) { setRows(null); setError(cause instanceof Error ? cause.message : 'Comments could not be loaded.') } })
    return () => controller.abort()
  }, [active, documentId, validFinding, attempt])
  if (!saved) return null
  const blocked = busy || review.actionPending || review.conflict || review.dirty || review.settingsDirty || review.scan?.status === 'scanning'
  return <section className="collaboration-section collaboration-discussion" aria-label="Finding discussion">
    {review.activeFindings.length === 0 ? <div className="collaboration-empty-team"><MessageSquare size={26} strokeWidth={1.4} aria-hidden="true" /><h3>No findings to discuss yet</h3><p>Run a check or mark a detail in the document. You can then start a discussion about that finding.</p></div> : <>
      <div className="collaboration-section-heading"><h3>Discuss a finding</h3></div>
      <p className="collaboration-description">Comments are visible to you and the currently assigned reviewer.</p>
      <div className="collaboration-reviewer-field"><label htmlFor="comment-finding">Finding</label>
        <StudioSelect id="comment-finding" value={validFinding} disabled={busy} onValueChange={id => { onFindingChange(id); setRows(null); setError(''); setRemoving(null) }}>
          <option value="">Choose a finding</option>
          {review.activeFindings.map((item, index) => <option key={item.finding_id} value={item.finding_id}>{index + 1} · {categoryPresentation[item.category].label}</option>)}
        </StudioSelect>
      </div>
      {selected && <>
        <div className="collaboration-finding-context"><span>Original detail</span><p>{review.codePoints.slice(selected.span.start, selected.span.end).join('')}</p></div>
        {active && rows === null && !error && <LoadingState key={validFinding} label="Loading discussion…" compact />}
        {rows?.length === 0 && <p className="collaboration-no-comments">No comments yet. Start the conversation below.</p>}
        <ol className="collaboration-comments">{rows?.map(row => <li key={row.id}>
          <header><strong>{row.is_mine ? 'You' : row.author_email}</strong><time dateTime={row.created_at} title={new Date(row.created_at).toLocaleString()}>{new Date(row.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} · {new Date(row.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
            {(row.is_mine || saved.can_edit) && <button type="button" className="collaboration-delete-comment" title="Delete comment" aria-label={`Delete comment by ${row.is_mine ? 'you' : row.author_email}`} disabled={blocked} onClick={() => setRemoving(row.id)}><Trash2 size={14} aria-hidden="true" /></button>}
          </header>
          <p>{row.text}</p>
          {removing === row.id && <div className="collaboration-delete-confirm" role="group" aria-label="Confirm comment deletion"><span>Delete this comment?</span><button type="button" disabled={busy} onClick={event => { setRemoving(null); event.currentTarget.closest('li')?.querySelector<HTMLButtonElement>('.collaboration-delete-comment')?.focus() }}>Cancel</button><button type="button" className="collaboration-danger" disabled={blocked} onClick={async () => {
            if (blocked) return
            onBusyChange(true); setOperation('delete'); setError('')
            try { await removeComment(saved.version.document_id, row.id, session.csrf_token); setRows(current => current?.filter(item => item.id !== row.id) ?? []); setRemoving(null) }
            catch (cause) { setError(cause instanceof Error ? cause.message : 'Comment could not be deleted.') }
            finally { setOperation(null); onBusyChange(false) }
          }}>{operation === 'delete' ? 'Deleting…' : 'Delete'}</button></div>}
        </li>)}</ol>
        <form className="collaboration-composer" onSubmit={async event => {
          event.preventDefault()
          if (blocked || !draft || !text.trim() || rows === null) return
          onBusyChange(true); setOperation('post'); setError('')
          try {
            const comment = await postComment(saved.version.document_id, validFinding, saved.version, draft.id, text, session.csrf_token)
            onDraftChange(validFinding, ''); setRows(current => current?.some(row => row.id === comment.id) ? current : [...(current ?? []), comment])
          } catch (cause) { setError(cause instanceof Error ? cause.message : 'Comment could not be posted. Your draft is kept here.') }
          finally { setOperation(null); onBusyChange(false); requestAnimationFrame(() => composerRef.current?.focus()) }
        }}>
          <label htmlFor="finding-comment">Add a comment</label>
          <GlassTextarea ref={composerRef} id="finding-comment" value={text} placeholder="Ask a question or explain a decision…" maxLength={2000} disabled={blocked} onChange={event => onDraftChange(validFinding, event.target.value)} aria-describedby="collaboration-draft-note" />
          <div className="collaboration-composer-footer"><span id="collaboration-draft-note">{text ? 'Draft kept when you close this panel' : 'Keep comments relevant to this finding'}<small>{text.length.toLocaleString()} / 2,000</small></span><button type="submit" className="studio-primary" disabled={blocked || !text.trim() || rows === null}>{operation === 'post' ? 'Posting…' : 'Post comment'}</button></div>
        </form>
        {blocked && !busy && <p className="collaboration-note" role="status">Save or reload your document changes before posting a comment.</p>}
      </>}
      {error && <InlineNotice error title="Check the discussion" actions={<button type="button" disabled={busy} onClick={() => { setError(''); setRows(null); setAttempt(value => value + 1) }}>Reload discussion</button>}>{error}</InlineNotice>}
    </>}
  </section>
}
