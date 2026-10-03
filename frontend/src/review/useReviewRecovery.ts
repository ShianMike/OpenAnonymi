import { extras } from '../detection/categories'
import type { Dispatch, SetStateAction } from 'react'
import type { FindingCategory, SessionView } from '../api/client'
import { useProtectedDraft } from '../recovery/useProtectedDraft'
import type { DraftState } from './reviewState'

type Update<T> = Dispatch<SetStateAction<T>>

export function useReviewRecovery({ state, documentId, session, text, categories,
  phoneRegion, language, dirty, paused, setText, setEmailEnabled, setPhoneEnabled, setExtraCategories,
  setPhoneRegion, setLanguage, setEditingSource, setConflict, setNotice }: {
  state: DraftState; documentId: string | undefined; session: SessionView
  text: string; categories: FindingCategory[]; phoneRegion: string; language: string
  dirty: boolean; paused: boolean
  setExtraCategories: Update<FindingCategory[]>; setText: Update<string>; setEmailEnabled: Update<boolean>; setPhoneEnabled: Update<boolean>
  setPhoneRegion: Update<string>; setLanguage: Update<string>; setEditingSource: Update<boolean>
  setConflict: Update<boolean>; setNotice: Update<string | null>
}) {
  const valid = state.kind === 'ready' && state.saved.can_edit && state.saved.version.document_id === documentId
  return useProtectedDraft({
    scope: valid && state.kind === 'ready' && documentId ? {
      userId: session.user_id, workspaceId: state.saved.workspace_id, documentId,
    } : null,
    csrf: session.csrf_token, dirty, paused,
    payload: valid && state.kind === 'ready' ? {
      source: text, title: state.saved.title, categories, phone_region: phoneRegion, language,
      retention_days: 7, preset_id: state.saved.preset_id, base_version: state.saved.version,
    } : null,
    onRestore: (view) => {
      if (state.kind !== 'ready') return
      setText(view.payload.source)
      setEmailEnabled(view.payload.categories.includes('email'))
      setPhoneEnabled(view.payload.categories.includes('phone'))
      setExtraCategories(extras(view.payload.categories))
      setPhoneRegion(view.payload.phone_region)
      setLanguage(view.payload.language ?? 'en')
      if (view.payload.source !== state.saved.text) setEditingSource(true)
      if (view.payload.base_version?.source_revision_id !== state.saved.version.source_revision_id) {
        setConflict(true)
        setNotice('Working draft recovered from an older source revision. Compare it with the latest saved text before applying your edits.')
      } else setNotice('Your working draft was recovered. Apply its changes when ready, then review the updated output.')
    },
  })
}
