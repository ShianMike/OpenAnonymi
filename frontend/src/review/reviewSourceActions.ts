import type { Dispatch, FormEvent, SetStateAction } from 'react'
import {
  ApiConflictError,
  ApiRequestError,
  saveDraftSource,
  type SavedDraftView,
} from '../api/client'
import { messageFrom, type DraftState } from './reviewState'

type Update<T> = Dispatch<SetStateAction<T>>

export function createReviewSourceActions({
  documentId,
  state,
  text,
  csrfToken,
  blocked,
  setPending,
  setError,
  setNotice,
  setConflict,
  onSaved,
}: {
  documentId: string | undefined
  state: DraftState
  text: string
  csrfToken: string
  blocked: boolean
  setPending: Update<boolean>
  setError: Update<string | null>
  setNotice: Update<string | null>
  setConflict: Update<boolean>
  onSaved: (saved: SavedDraftView, text: string) => Promise<void>
}) {
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!documentId || state.kind !== 'ready' || blocked || text === state.saved.text) return
    setPending(true)
    setError(null)
    setNotice(null)
    try {
      const saved = await saveDraftSource(documentId, state.saved.version, text, csrfToken)
      await onSaved(saved, text)
      setNotice('Draft saved as a new source revision. Review it again before export.')
    } catch (cause) {
      if (cause instanceof ApiConflictError) {
        setConflict(true)
      } else if (
        cause instanceof TypeError ||
        (cause instanceof ApiRequestError && [502, 504].includes(cause.status))
      ) {
        setError(
          'The save could not be confirmed. Your edits remain in this tab. Retry when the connection returns, or copy them before reloading.',
        )
      } else setError(messageFrom(cause))
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

  return { save, copyUnsaved }
}
