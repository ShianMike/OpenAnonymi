import type { Dispatch, SetStateAction } from 'react'
import {
  ApiConflictError,
  confirmReview,
  downloadReviewedFile,
  getCopyPayload,
  getReviewSummary,
  recordCopySuccess,
  type SessionView,
  type ReviewSummaryView,
  type VersionRef,
} from '../api/client'
import { messageFrom, sameVersion, type DraftState } from './reviewState'

type Update<T> = Dispatch<SetStateAction<T>>
type ExportContext = {
  documentId: string | undefined
  session: SessionView
  state: DraftState
  canConfirm: boolean
  canExport: boolean
  confirmedPreview: boolean
  setCompletionPending: Update<boolean>
  setError: Update<string | null>
  setNotice: Update<string | null>
  setState: Update<DraftState>
  setConfirmedPreview: Update<boolean>
  setSummary: Update<ReviewSummaryView | null>
  setConflict: Update<boolean>
  setExportPending: Update<boolean>
  setPreparedDownload: Update<{ url: string; filename: string; version: VersionRef; format: 'txt' | 'docx' } | null>
}

/** Completion and export share the server's version-bound review contract. */
export function createReviewExportActions({
  documentId,
  session,
  state,
  canConfirm,
  canExport,
  confirmedPreview,
  setCompletionPending,
  setError,
  setNotice,
  setState,
  setConfirmedPreview,
  setSummary,
  setConflict,
  setExportPending,
  setPreparedDownload,
}: ExportContext) {
  async function completeReview() {
    if (!documentId || state.kind !== 'ready' || !canConfirm || !confirmedPreview) return
    setCompletionPending(true)
    setError(null)
    setNotice(null)
    try {
      const completed = await confirmReview(documentId, state.saved.version, session.csrf_token)
      setState({ kind: 'ready', saved: { ...state.saved, status: completed.status } })
      setConfirmedPreview(false)
      setNotice('Review confirmed. Export will unlock when the required approvals are complete.')
      try {
        const result = await getReviewSummary(documentId)
        if (sameVersion(result.version, state.saved.version)) setSummary(result)
      } catch {
        setError('Review confirmed, but the summary could not be loaded. Reload to retry it.')
      }
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setCompletionPending(false)
    }
  }

  async function copyReviewedOutput() {
    if (!documentId || state.kind !== 'ready' || !canExport) return
    setExportPending(true)
    setError(null)
    setNotice(null)
    try {
      const payload = await getCopyPayload(documentId, state.saved.version, session.csrf_token)
      try {
        await navigator.clipboard.writeText(payload.text)
      } catch {
        setError('The browser could not copy the reviewed text. Nothing was recorded as copied.')
        return
      }
      try {
        await recordCopySuccess(
          documentId,
          payload.version,
          payload.completion_id,
          crypto.randomUUID(),
          session.csrf_token,
        )
        setState({ kind: 'ready', saved: { ...state.saved, status: 'exported' } })
        setNotice('Reviewed text copied to the clipboard.')
        try {
          const result = await getReviewSummary(documentId)
          if (sameVersion(result.version, state.saved.version)) setSummary(result)
        } catch {
          setError('Text copied, but the review summary could not be refreshed.')
        }
      } catch {
        setError(
          'Text was copied, but its activity record could not be confirmed. Reload before trying again.',
        )
      }
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setExportPending(false)
    }
  }

  async function downloadReviewedOutput(format: 'txt' | 'docx' = 'txt') {
    if (!documentId || state.kind !== 'ready' || !canExport) return
    setExportPending(true)
    setError(null)
    setNotice(null)
    try {
      const file = await downloadReviewedFile(
        documentId,
        state.saved.version,
        crypto.randomUUID(),
        session.csrf_token,
        format,
      )
      setState({ kind: 'ready', saved: { ...state.saved, status: 'exported' } })
      setPreparedDownload({
        url: URL.createObjectURL(file),
        filename: `reviewed-${documentId}.${format}`,
        version: state.saved.version,
        format,
      })
      setNotice(`Reviewed ${format === 'txt' ? 'TXT' : 'Word file'} generated. Use the save link to download it.`)
      try {
        const result = await getReviewSummary(documentId)
        if (sameVersion(result.version, state.saved.version)) setSummary(result)
      } catch {
        setError('Output generated, but the review summary could not be refreshed.')
      }
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setExportPending(false)
    }
  }

  return { completeReview, copyReviewedOutput, downloadReviewedOutput }
}
