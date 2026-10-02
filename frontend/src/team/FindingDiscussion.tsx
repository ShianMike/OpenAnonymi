import { useEffect, useRef, useState } from 'react'
import { MessageSquare } from 'lucide-react'
import type { SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { GlassSelect } from '../ui/GlassSelect'
import { GlassTextarea } from '../ui/GlassTextarea'
import { InlineNotice, PanelHeading } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { getComments, postComment, removeComment, type CommentView } from './api'

export function FindingDiscussion({ review, session }: { review: ReviewController; session: SessionView }) {
  const [finding, setFinding] = useState(review.selectedFindingId ?? review.activeFindings[0]?.finding_id ?? '')
  const [rows, setRows] = useState<CommentView[] | null>(null)
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const retryId = useRef<string | null>(null)
  const saved = review.state.kind === 'ready' ? review.state.saved : null
  const validFinding = review.activeFindings.some((item) => item.finding_id === finding) ? finding : ''
  const documentId = saved?.version.document_id
  useEffect(() => {
    if (!documentId || !validFinding) return
    const controller = new AbortController()
    getComments(documentId, validFinding, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setRows(value) })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Comments could not be loaded.') })
    return () => controller.abort()
  }, [documentId, validFinding, attempt])
  if (!saved || !review.activeFindings.length) return null
  const blocked = pending || review.actionPending || review.conflict || review.dirty || review.settingsDirty
  return <details className="team-discussion team-panel workspace-panel">
    <summary><MessageSquare size={16} aria-hidden="true" /> Finding discussion</summary>
    <div className="team-discussion-body">
      <PanelHeading icon={MessageSquare} title="Comments" description="Only the owner and currently assigned reviewer can read this discussion." />
      <label htmlFor="comment-finding">Finding</label>
      <GlassSelect id="comment-finding" value={validFinding} disabled={pending} onValueChange={(id) => {
        setFinding(id); setRows(null); setText(''); setError(null); retryId.current = null
      }}>
        <option value="">Choose a finding</option>
        {review.activeFindings.map((item, index) => <option key={item.finding_id} value={item.finding_id}>{index + 1} · {item.category} · {item.action || 'Pending'}</option>)}
      </GlassSelect>
      {validFinding && <>
        {rows === null && !error && <LoadingState label="Loading comments…" compact />}
        {rows?.length === 0 && <p className="field-note">No comments yet. Start a conversation about this detail.</p>}
        <ol className="team-comment-list">{rows?.map((row) => <li key={row.id}>
          <div><strong>{row.is_mine ? 'You' : row.author_email}</strong><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time></div>
          <p>{row.text}</p>
          {(row.is_mine || saved.can_edit) && <button type="button" disabled={blocked} onClick={async () => {
            setPending(true); setError(null)
            try { await removeComment(saved.version.document_id, row.id, session.csrf_token); setRows((current) => current?.filter((item) => item.id !== row.id) ?? []) }
            catch (cause) { setError(cause instanceof Error ? cause.message : 'Comment could not be removed.') }
            finally { setPending(false) }
          }}>Remove comment</button>}
        </li>)}</ol>
        <form onSubmit={async (event) => {
          event.preventDefault(); setPending(true); setError(null)
          retryId.current ??= crypto.randomUUID()
          try {
            await postComment(saved.version.document_id, validFinding, saved.version, retryId.current, text, session.csrf_token)
            retryId.current = null; setText(''); setRows(null); setAttempt(attempt + 1)
          } catch (cause) { setError(cause instanceof Error ? cause.message : 'Comment could not be saved. Your text remains here.') }
          finally { setPending(false) }
        }}>
          <label htmlFor="finding-comment">Add a comment</label>
          <GlassTextarea id="finding-comment" value={text} maxLength={2000} disabled={blocked} onChange={(event) => { setText(event.target.value); retryId.current = null }} />
          <button type="submit" disabled={blocked || !text.trim() || rows === null}>Post comment</button>
        </form>
      </>}
      {error && <InlineNotice error>{error}<button type="button" onClick={() => { setError(null); setRows(null); setAttempt(attempt + 1) }}>Retry comments</button></InlineNotice>}
    </div>
  </details>
}
