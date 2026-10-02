import type { Dispatch, SetStateAction } from 'react'
import { ApiConflictError, getDraft, getScan, getFindings, getPreview, getReviewSummary, startScan, updateScanSettings,
  type FindingCategory, type FindingsView, type PreviewView, type ReviewSummaryView, type ScanView, type VersionRef } from '../api/client'
import { messageFrom, sameVersion, type DraftState } from './reviewState'
import type { ProtectedDraftController } from '../recovery/useProtectedDraft'

type Update<T> = Dispatch<SetStateAction<T>>
type Download = { url: string; filename: string; version: VersionRef } | null

export function createReviewScanActions({ documentId, state, dirty, settingsDirty, selectedCategories, phoneRegion,
  csrf, recovery, refreshPreview, setScanPending, setError, setNotice, setScan, setUndoCount, setSummary,
  setConfirmedPreview, setPreparedDownload, setState, setFindings, setConflict, setSettingsPending, setPreview, setPreviewError }: {
  documentId: string | undefined; state: DraftState; dirty: boolean; settingsDirty: boolean;
  selectedCategories: FindingCategory[]; phoneRegion: string; csrf: string; recovery: ProtectedDraftController;
  refreshPreview: (id: string, version: VersionRef) => Promise<void>;
  setScanPending: Update<boolean>; setError: Update<string | null>; setNotice: Update<string | null>;
  setScan: Update<ScanView | null>; setUndoCount: Update<number>; setSummary: Update<ReviewSummaryView | null>;
  setConfirmedPreview: Update<boolean>; setPreparedDownload: Update<Download>; setState: Update<DraftState>;
  setFindings: Update<FindingsView | null>; setConflict: Update<boolean>; setSettingsPending: Update<boolean>;
  setPreview: Update<PreviewView | null>; setPreviewError: Update<string | null>;
}) {
  async function scanDraft() {
    if (!documentId || state.kind !== 'ready' || !state.saved.can_edit) {
      setError('The saved draft is not ready to scan. Reload it and try again.')
      return
    }
    if (dirty || settingsDirty) {
      setError('Save the text and suggestion settings before scanning.')
      return
    }
    setScanPending(true)
    setError(null)
    setNotice(null)
    try {
      const result = await startScan(documentId, state.saved.version, csrf)
      setScan(result)
      setUndoCount(0)
      if (result.status === 'completed') {
        setSummary(null)
        setConfirmedPreview(false)
        setPreparedDownload(null)
        setState({
          kind: 'ready',
          saved: {
            ...state.saved,
            version: result.version,
            status: 'needs_review',
          },
        })
        setNotice(
          result.match_count === 0
            ? null
            : 'Suggestions are unresolved. Review every occurrence before export.',
        )
      } else {
        setNotice('A scan is in progress. Refresh its status shortly.')
      }
      try {
        setFindings(await getFindings(documentId))
      } catch {
        setFindings(null)
        setError('The scan was saved, but findings could not be refreshed. Reload the draft.')
      }
      await refreshPreview(documentId, result.version)
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
      getScan(documentId)
        .then(setScan)
        .catch(() => undefined)
    } finally {
      setScanPending(false)
    }
  }

  async function saveSettings() {
    if (!documentId || state.kind !== 'ready' || !state.saved.can_edit || dirty || !settingsDirty) return
    setSettingsPending(true)
    setError(null)
    try {
      const updated = await updateScanSettings(
        documentId,
        state.saved.version,
        selectedCategories,
        phoneRegion,
        csrf,
      )
      setState({
        kind: 'ready',
        saved: {
          ...state.saved,
          version: updated.version,
          status: 'draft',
          categories: selectedCategories,
          phone_region: phoneRegion,
        },
      })
      setScan({
        version: updated.version,
        status: 'not_started',
        attempt_count: 0,
        match_count: null,
        failure_code: null,
        suggestions: [],
      })
      setFindings(null)
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      try {
        setFindings(await getFindings(documentId))
      } catch {
        setError('Settings were saved, but findings could not be refreshed. Reload the draft.')
      }
      await refreshPreview(documentId, updated.version)
      setUndoCount(0)
      await recovery.clear().catch(() => undefined)
      setNotice('Suggestion settings saved. Run a fresh scan before review.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setSettingsPending(false)
    }
  }

  async function refreshScan() {
    if (!documentId || dirty) return
    try {
      const [latest, scanResult, findingResult, previewResult] = await Promise.all([
        getDraft(documentId),
        getScan(documentId),
        getFindings(documentId),
        getPreview(documentId),
      ])
      if (
        !sameVersion(latest.version, scanResult.version) ||
        !sameVersion(latest.version, findingResult.version) ||
        !sameVersion(latest.version, previewResult.version)
      ) {
        throw new Error('The review changed while refreshing. Retry to get one current version.')
      }
      setState({ kind: 'ready', saved: latest })
      setScan(scanResult)
      setFindings(findingResult)
      setPreview(previewResult)
      setPreviewError(null)
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setUndoCount(0)
      setError(null)
      if (latest.status === 'ready' || latest.status === 'exported') {
        try {
          const currentSummary = await getReviewSummary(documentId)
          if (sameVersion(currentSummary.version, latest.version)) setSummary(currentSummary)
        } catch {
          setError('The review loaded, but its summary could not be refreshed.')
        }
      }
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    }
  }

  return { scanDraft, saveSettings, refreshScan }
}
