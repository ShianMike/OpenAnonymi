import { createReviewDecisionActions } from './reviewDecisionActions'
import { createReviewCsvActions } from './reviewCsvActions'
import { useUndoState } from './useUndoState'
import { createReviewScanActions } from './reviewScanActions'
import { useReviewHandoff } from '../team/useReviewHandoff'
import { useReviewStateLoader, type ReviewStateView } from './useReviewStateLoader'
import { extras } from '../detection/categories'
import { createReviewExportActions } from './reviewExportActions'
import { createReviewSourceActions } from './reviewSourceActions'
import { useSourceRecovery } from './useSourceRecovery'
import { useReviewRecovery } from './useReviewRecovery'
import { useReviewResume } from '../resume/useReviewResume'
import { forgetReview } from '../resume/lastReview'
import { createReviewNavigation } from './reviewNavigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  ApiConflictError,
  addManualFinding,
  getDraft,
  getExactMatches,
  getPreview,
  getScan,
  removeFinding,
  reviseFinding,
  type ExactMatchesView,
  type FindingCategory,
  type FindingsView,
  type PreviewView,
  type ReviewSummaryView,
  type ScanView,
  type SessionView,
  type SourceSpan,
  type VersionRef,
} from '../api/client'
import { utf16OffsetToCodePoint } from './offsets'

import {
  messageFrom,
  sameVersion,
  sameScanVersion,
  type DraftState,
  type GroupConfirmation,
  type ReviewedDownload,
} from './reviewState'

export function useReviewController(session: SessionView) {
  const { documentId } = useParams<{ documentId: string }>()
  const workspaceIds = session.memberships.map((item) => item.workspace_id).join(',')
  const [loadedState, setState] = useState<DraftState>({ kind: 'loading' })
  const state: DraftState = loadedState.kind === 'ready' &&
    loadedState.saved.version.document_id !== documentId ? { kind: 'loading' } : loadedState
  const [text, setText] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [scan, setScan] = useState<ScanView | null>(null)
  const [findings, setFindings] = useState<FindingsView | null>(null)
  const [preview, setPreview] = useState<PreviewView | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [summary, setSummary] = useState<ReviewSummaryView | null>(null)
  const [initialHandoff, setInitialHandoff] = useState<ReviewStateView['handoff'] | null>(null)
  const [confirmedPreview, setConfirmedPreview] = useState(false)
  const [completionPending, setCompletionPending] = useState(false)
  const [exportPending, setExportPending] = useState(false)
  const [preparedDownload, setPreparedDownload] = useState<ReviewedDownload | null>(null)
  const sourceRef = useRef<HTMLTextAreaElement>(null)
  const previewRef = useRef<HTMLTextAreaElement>(null)
  const groupConfirmRef = useRef<HTMLButtonElement>(null)
  const groupTriggerRef = useRef<HTMLButtonElement | null>(null)
  const lastFocusedRef = useRef<HTMLElement | null>(null)
  const wasPendingRef = useRef(false)
  const [selection, setSelection] = useState<SourceSpan | null>(null)
  const [manualCategory, setManualCategory] = useState<FindingCategory>('person')
  const [categoryFilter, setCategoryFilter] = useState<FindingCategory | 'all'>('all')
  const [decisionFilter, setDecisionFilter] = useState<'all' | 'pending' | 'decided'>('all')
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [mobilePanel, setMobilePanel] = useState<'original' | 'preview' | 'findings'>('original')
  const [editingSource, setEditingSource] = useState(false)
  const [plainPreview, setPlainPreview] = useState(false)
  const [findingPending, setFindingPending] = useState(false)
  const undoCount = useUndoState(findings, state.kind === 'ready' ? state.saved.version : null)
  const [exactMatches, setExactMatches] = useState<{
    findingId: string
    result: ExactMatchesView
  } | null>(null)
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({})
  const [keepReason, setKeepReason] = useState<'false_match' | 'intended_disclosure'>('false_match')
  const [groupConfirmation, setGroupConfirmation] = useState<GroupConfirmation | null>(null)
  const [scanPending, setScanPending] = useState(false)
  const [settingsPending, setSettingsPending] = useState(false)
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [extraCategories, setExtraCategories] = useState<FindingCategory[]>([])
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [language, setLanguage] = useState('en')
  const canEdit = state.kind === 'ready' && state.saved.can_edit
  const canManagePresets = state.kind === 'ready' && session.memberships.some(
    (item) => item.workspace_id === state.saved.workspace_id && item.role === 'administrator',
  )
  const handoff = useReviewHandoff({ saved: state.kind === 'ready' ? state.saved : null, initial: initialHandoff,
    onChanged: () => setConflict(true),
    onUnavailable: (message) => {
      if (state.kind === 'ready' && documentId) forgetReview(session.user_id, state.saved.workspace_id, documentId)
      setState({ kind: 'error', message, retryable: false }); setText(''); setFindings(null); setPreview(null); setPreparedDownload(null)
    },
  })
  const dirty = state.kind === 'ready' && text !== state.saved.text
  const selectedCategories: FindingCategory[] = [
    ...(emailEnabled ? ['email' as const] : []),
    ...(phoneEnabled ? ['phone' as const] : []), ...extraCategories,
  ].sort() as FindingCategory[]
  const settingsDirty = state.kind === 'ready' &&
    (state.saved.categories.join(',') !== selectedCategories.join(',') ||
      state.saved.phone_region !== phoneRegion || state.saved.language !== language)
  const recovery = useReviewRecovery({
    state, documentId, session, text, categories: selectedCategories, phoneRegion, language,
    dirty: dirty || settingsDirty,
    paused: pending || settingsPending,
    setText, setEmailEnabled, setPhoneEnabled, setExtraCategories, setPhoneRegion, setLanguage, setEditingSource,
    setConflict, setNotice,
  })
  const mutationPending =
    pending ||
    completionPending ||
    exportPending ||
    findingPending ||
    scanPending ||
    settingsPending || recovery.loading

  const sourceRecovery = useSourceRecovery({
    documentId,
    state,
    enabled: conflict && !mutationPending,
    applyLatest: ({ saved, scan, findings, preview }) => {
      setState({ kind: 'ready', saved })
      setScan(scan)
      setFindings(findings)
      setPreview(preview)
      setPreviewError(null)
      resetSourceReview()
      if (!settingsDirty) {
        setEmailEnabled(saved.categories.includes('email'))
        setPhoneEnabled(saved.categories.includes('phone'))
        setExtraCategories(extras(saved.categories))
        setPhoneRegion(saved.phone_region)
        setLanguage(saved.language)
      }
      setConflict(false)
      setError(null)
      setNotice(
        'Latest saved review loaded. Your editor text is kept. Save a new revision when ready, then review its findings again.',
      )
      requestAnimationFrame(() => sourceRef.current?.focus({ preventScroll: true }))
    },
  })
  const actionPending = mutationPending || sourceRecovery.pending

  useEffect(() => {
    if (actionPending) {
      wasPendingRef.current = true
      return
    }
    if (!wasPendingRef.current) return
    wasPendingRef.current = false
    const frame = requestAnimationFrame(() => {
      if (document.activeElement !== document.body) return
      const previous = lastFocusedRef.current
      const canFocus = (element: HTMLElement | null | undefined) =>
        element?.isConnected && !element.matches(':disabled') && element.getClientRects().length > 0
      const summary = previous?.closest('details')?.querySelector<HTMLElement>('summary')
      if (canFocus(previous)) previous?.focus()
      else if (canFocus(summary)) summary?.focus()
      else if (canFocus(sourceRef.current)) sourceRef.current?.focus()
      else
        document
          .querySelector<HTMLElement>('.review-panel-switch button[data-state="active"]')
          ?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [actionPending])

  useEffect(() => {
    if (groupConfirmation) groupConfirmRef.current?.focus()
  }, [groupConfirmation])

  useReviewStateLoader({ documentId, attempt, workspaceIds, userId: session.user_id,
    onLoaded: ({ source: saved, scan: scanResult, findings: findingResult, preview: previewResult, summary, handoff }) => {
        setState({ kind: 'ready', saved })
        setText(saved.text)
        setEmailEnabled(saved.categories.includes('email'))
        setPhoneEnabled(saved.categories.includes('phone'))
        setExtraCategories(extras(saved.categories))
        setPhoneRegion(saved.phone_region)
        setLanguage(saved.language)
        setScan(scanResult)
        setFindings(findingResult)
        setPreview(previewResult)
        setPreviewError(null)
        setSummary(summary)
        setInitialHandoff(handoff)
        setConfirmedPreview(false)
        setSelection(null)
        setExactMatches(null)
        setSelectedFindingId(null)
        setEditingSource(false)
        setPlainPreview(false)
        setError(null)
        setConflict(false)
    }, onError: setState,
  })

  async function refreshPreview(id: string, expected: VersionRef) {
    setPreview(null)
    setPreviewError(null)
    try {
      const result = await getPreview(id)
      if (!sameVersion(result.version, expected)) {
        setConflict(true)
        setPreviewError('The review changed while loading the preview. Reload the saved version.')
        return
      }
      setPreview(result)
    } catch (cause: unknown) {
      setPreviewError(messageFrom(cause))
    }
  }

  useEffect(() => {
    return () => {
      if (preparedDownload) URL.revokeObjectURL(preparedDownload.url)
    }
  }, [preparedDownload])

  function resetSourceReview() {
    setSummary(null)
    setConfirmedPreview(false)
    setPreparedDownload(null)
    setSelection(null)
    setExactMatches(null)
    setSelectedFindingId(null)
    setGroupConfirmation(null)
    setMergeTargets({})
  }

  const { save, copyUnsaved } = createReviewSourceActions({
    documentId,
    state,
    text,
    csrfToken: session.csrf_token,
    blocked: actionPending || conflict || !canEdit,
    setPending,
    setError,
    setNotice,
    setConflict,
    onSaved: async (saved, source) => {
      if (state.kind !== 'ready' || !documentId) return
      let csv = state.saved.csv
      if (csv) {
        resetSourceReview()
        setPreview(null)
        setFindings(null)
        try {
          const latest = await getDraft(documentId)
          if (!sameVersion(latest.version, saved.version) || !latest.csv) throw new Error('Review changed.')
          csv = latest.csv
        } catch {
          setConflict(true)
          throw new Error('Source saved, but its CSV cells could not be refreshed. Reload the saved review.')
        }
      }
      await recovery.clear().catch(() => {
        setNotice('Source saved. An older working backup remains available until it expires.')
      })
      setState({
        kind: 'ready',
        saved: {
          ...state.saved,
          version: saved.version,
          text: source,
          status: saved.status,
          expires_at: saved.expires_at,
          structure: saved.structure,
          csv,
        },
      })
      setConflict(false)
      sourceRecovery.cancel()
      setScan({
        version: saved.version,
        status: 'not_started',
        attempt_count: 0,
        match_count: null,
        dropped_suggestions: 0,
        failure_code: null,
        suggestions: [],
      })
      setFindings({ version: saved.version, findings: [], overlaps: [], undo_available: 0 })
      resetSourceReview()
      await refreshPreview(documentId, saved.version)
    },
  })

  async function reloadSaved() {
    if (dirty || settingsDirty) {
      try { await recovery.clear() }
      catch (cause) {
        setError(messageFrom(cause))
        return
      }
    }
    sourceRecovery.cancel()
    setPending(false)
    setError(null)
    setNotice(null)
    setConflict(false)
    setState({ kind: 'loading' })
    setScan(null)
    setFindings(null)
    setPreview(null)
    setPreviewError(null)
    setSummary(null)
    setConfirmedPreview(false)
    setPreparedDownload(null)
    setSelection(null)
    setExactMatches(null)
    setSelectedFindingId(null)
    setAttempt((value) => value + 1)
  }

  const { scanDraft, saveSettings, refreshScan } = createReviewScanActions({
    documentId, state, dirty, settingsDirty, selectedCategories, phoneRegion, language, csrf: session.csrf_token,
    recovery, refreshPreview, setScanPending, setError, setNotice, setScan, setSummary,
    setConfirmedPreview, setPreparedDownload, setState, setFindings, setConflict, setSettingsPending, setPreview, setPreviewError,
  })

  const savedText = state.kind === 'ready' ? state.saved.text : ''
  const codePoints = useMemo(() => Array.from(savedText), [savedText])
  const activeFindings = useMemo(() => findings?.findings || [], [findings])
  const selectionOverlaps = Boolean(
    selection &&
    activeFindings.some(
      (item) => selection.start < item.span.end && item.span.start < selection.end,
    ),
  )
  const visibleFindings = useMemo(() => activeFindings.filter(
    (item) =>
      (categoryFilter === 'all' || item.category === categoryFilter) &&
      (decisionFilter === 'all' ||
        (decisionFilter === 'pending' ? item.action === null : item.action !== null)),
  ), [activeFindings, categoryFilter, decisionFilter])
  const pendingFindings = useMemo(() => activeFindings.filter((item) => item.action === null), [activeFindings])
  useReviewResume({
    userId: session.user_id, documentId,
    workspaceId: state.kind === 'ready' ? state.saved.workspace_id : null,
    ready: state.kind === 'ready' && state.saved.version.document_id === documentId && !recovery.loading,
    revision: state.kind === 'ready' ? state.saved.version.source_revision_id : null,
    dirty,
    findingIds: activeFindings.map((item) => item.finding_id),
    location: { panel: mobilePanel, category: categoryFilter, decision: decisionFilter,
      finding: selectedFindingId, editing: editingSource, plainPreview },
    apply: (saved) => {
      setMobilePanel(saved.editing && dirty ? 'original' : saved.panel)
      setCategoryFilter(saved.category)
      setDecisionFilter(saved.decision)
      setSelectedFindingId(saved.finding)
      setEditingSource(saved.editing)
      setPlainPreview(saved.plainPreview)
    },
  })
  const currentReview =
    state.kind === 'ready' &&
    !dirty &&
    !settingsDirty &&
    !conflict &&
    !pending &&
    !settingsPending &&
    !scanPending &&
    !findingPending &&
    !completionPending &&
    !exportPending &&
    scan?.status === 'completed' &&
    sameScanVersion(scan.version, state.saved.version) &&
    findings !== null &&
    sameVersion(findings.version, state.saved.version) &&
    findings.overlaps.length === 0 &&
    pendingFindings.length === 0 &&
    preview?.status === 'complete' &&
    preview.text !== null &&
    sameVersion(preview.version, state.saved.version)
  const canConfirm =
    canEdit && state.kind === 'ready' && currentReview && state.saved.status === 'needs_review'
  const canExport =
    canEdit && handoff.exportApproved &&
    state.kind === 'ready' &&
    currentReview &&
    (state.saved.status === 'ready' || state.saved.status === 'exported')
  const currentSummary =
    state.kind === 'ready' && summary && sameVersion(summary.version, state.saved.version)
      ? summary
      : null
  const groupMembers = useMemo(() => {
    const members = new Map<string, typeof activeFindings>()
    for (const item of activeFindings) {
      if (!item.group_id) continue
      const group = members.get(item.group_id)
      if (group) group.push(item)
      else members.set(item.group_id, [item])
    }
    return members
  }, [activeFindings])

  function captureSelection(event: React.SyntheticEvent<HTMLTextAreaElement>) {
    const element = event.currentTarget
    if (element.selectionStart === element.selectionEnd || state.kind !== 'ready') {
      setSelection(null)
      setExactMatches(null)
      return
    }
    try {
      setSelection({
        start: utf16OffsetToCodePoint(text, element.selectionStart),
        end: utf16OffsetToCodePoint(text, element.selectionEnd),
      })
    } catch {
      setSelection(null)
    }
  }

  async function changeFinding(kind: 'add' | 'revise' | 'remove', findingId?: string) {
    if (actionPending || conflict) return
    if (!documentId || state.kind !== 'ready') {
      setError('Reload the saved draft before changing findings.')
      return
    }
    if (dirty || settingsDirty) {
      setError('Save the text and suggestion settings before changing findings.')
      return
    }
    if (kind !== 'remove' && !selection) {
      setError('Select an exact range in the saved text first.')
      return
    }
    if (kind !== 'add' && !findingId) {
      setError('Choose an existing finding to change.')
      return
    }
    setFindingPending(true)
    setError(null)
    setNotice(null)
    try {
      const result =
        kind === 'add'
          ? await addManualFinding(
              documentId,
              state.saved.version,
              selection as SourceSpan,
              manualCategory,
              session.csrf_token,
            )
          : kind === 'revise'
            ? await reviseFinding(
                documentId,
                findingId as string,
                state.saved.version,
                selection as SourceSpan,
                manualCategory,
                session.csrf_token,
              )
            : await removeFinding(
                documentId,
                findingId as string,
                state.saved.version,
                session.csrf_token,
              )
      setFindings(result)
      if (
        selectedFindingId &&
        !result.findings.some((item) => item.finding_id === selectedFindingId)
      ) {
        setSelectedFindingId(null)
      }
      setState({
        kind: 'ready',
        saved: {
          ...state.saved,
          version: result.version,
          status: 'needs_review',
        },
      })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setSelection(null)
      setExactMatches(null)
      setGroupConfirmation(null)
      await refreshPreview(documentId, result.version)
      try {
        setScan(await getScan(documentId))
      } catch {
        setScan(null)
        setError('Finding saved, but the scan summary could not be refreshed. Reload the draft.')
      }
      setNotice('Finding changes saved. Review completion must use this latest version.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setFindingPending(false)
    }
  }

  async function showExactMatches(findingId: string) {
    if (!documentId || state.kind !== 'ready' || dirty || settingsDirty) return
    setError(null)
    try {
      setExactMatches({ findingId, result: await getExactMatches(documentId, findingId) })
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    }
  }

  const decisionActions = createReviewDecisionActions({
    documentId, state, findings, preview, dirty, settingsDirty, actionPending, conflict, mergeTargets,
    keepReason, csrf: session.csrf_token, undoCount, groupConfirmation,
    refreshPreview, setFindingPending, setError, setNotice, setFindings, setMergeTargets, setState,
    setSummary, setConfirmedPreview, setPreparedDownload, setExactMatches, setGroupConfirmation, setConflict,
  })

  const csvActions = createReviewCsvActions({
    state, blocked: actionPending || conflict || dirty || settingsDirty, canManagePresets,
    csrf: session.csrf_token, resetReview: resetSourceReview, refreshPreview, setState,
    setSettingsPending, setFindingPending, setError, setNotice, setConflict, setScan, setFindings,
  })
  const { changeReview, undoReview, useLatestDefaults } = decisionActions
  function confirmGroupDecision() { lastFocusedRef.current = groupTriggerRef.current; decisionActions.confirmGroupDecision() }
  function cancelGroupDecision() { decisionActions.cancelGroupDecision(); requestAnimationFrame(() => groupTriggerRef.current?.focus()) }

  const { locateFinding, nextUnresolved } = createReviewNavigation({
    state, findings, blocked: dirty || settingsDirty, selectedFindingId,
    setSelectedFindingId, setMobilePanel, setEditingSource, setPlainPreview,
    setCategoryFilter, setDecisionFilter,
  })

  const { completeReview, copyReviewedOutput, downloadReviewedOutput } = createReviewExportActions({
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
  })

  return {
    retentionCsrf: session.csrf_token,
    retentionRenewed: (id: string, expires: string) => {
      setState(current => current.kind === 'ready' && current.saved.version.document_id === id ? { ...current, saved: { ...current.saved, expires_at: expires } } : current)
      setNotice('Retention renewed. Your source, decisions and confirmation are preserved.')
    },
    canEdit,
    canManagePresets,
    ...csvActions,
    handoff,
    recovery,
    actionPending,
    activeFindings,
    canConfirm,
    canExport,
    cancelGroupDecision,
    captureSelection,
    categoryFilter,
    changeFinding,
    changeReview,
    codePoints,
    completeReview,
    completionPending,
    confirmGroupDecision,
    confirmedPreview,
    conflict,
    copyReviewedOutput,
    copyUnsaved,
    currentSummary,
    decisionFilter,
    dirty,
    editingSource,
    documentId,
    downloadReviewedOutput,
    emailEnabled,
    extraCategories,
    setExtraCategories,
    error,
    exactMatches,
    exportPending,
    findingPending,
    findings,
    groupConfirmRef,
    groupConfirmation,
    groupMembers,
    groupTriggerRef,
    keepReason,
    lastFocusedRef,
    locateFinding,
    manualCategory,
    mergeTargets,
    mobilePanel,
    nextUnresolved,
    notice,
    pending,
    pendingFindings,
    plainPreview,
    phoneEnabled,
    phoneRegion,
    language,
    setLanguage,
    preparedDownload,
    preview,
    previewError,
    previewRef,
    refreshPreview,
    refreshScan,
    reloadSaved,
    save,
    saveSettings,
    scan,
    scanDraft,
    scanPending,
    selectedFindingId,
    selection,
    selectionOverlaps,
    setCategoryFilter,
    setConfirmedPreview,
    setDecisionFilter,
    setEmailEnabled,
    setEditingSource,
    setGroupConfirmation,
    setKeepReason,
    setManualCategory,
    setMergeTargets,
    setMobilePanel,
    setNotice,
    setPhoneEnabled,
    setPhoneRegion,
    setPlainPreview,
    setPreparedDownload,
    setSelection,
    setSelectedFindingId,
    setText,
    settingsDirty,
    settingsPending,
    showExactMatches,
    sourceRecovery,
    sourceRef,
    state,
    summary,
    text,
    undoCount,
    undoReview,
    useLatestDefaults,
    visibleFindings,
  }
}

export type ReviewController = ReturnType<typeof useReviewController>
