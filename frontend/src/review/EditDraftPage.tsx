import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ApiConflictError, ApiRequestError, addExactMatch, addManualFinding, confirmReview, decideFindings,
  downloadReviewedTxt, getCopyPayload, getDraft, getExactMatches, getFindings, getPreview,
  getReviewSummary, getScan, getWorkspaceDocuments, mergeFindings, recordCopySuccess, removeFinding, reviseFinding,
  saveDraftSource, splitFinding, startScan, undoReviewEdit, updateScanSettings,
  type ExactMatchesView, type FindingCategory, type FindingsView, type PreviewView,
  type ReviewSummaryView, type ScanView, type SessionView, type SourceSpan, type SourceView,
  type VersionRef,
} from '../api/client'
import { codePointRangeToUtf16, utf16OffsetToCodePoint } from './offsets'
import { PageHeader } from '../ui/PageHeader'
import { StatusBadge } from '../ui/StatusBadge'

type DraftState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; retryable?: boolean }
  | { kind: 'ready'; saved: SourceView }

type GroupConfirmation = {
  findingId: string
  action: 'label' | 'redact' | 'keep'
  affectedIds: string[]
  spans: SourceSpan[]
  version: VersionRef
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

function sameVersion(left: VersionRef, right: VersionRef): boolean {
  return left.document_id === right.document_id &&
    left.source_revision_id === right.source_revision_id &&
    left.decision_version === right.decision_version &&
    left.settings_version === right.settings_version
}

function sameScanVersion(left: VersionRef, right: VersionRef): boolean {
  return left.document_id === right.document_id &&
    left.source_revision_id === right.source_revision_id &&
    left.settings_version === right.settings_version
}

export function EditDraftPage({ session }: { session: SessionView }) {
  const { documentId } = useParams<{ documentId: string }>()
  const workspaceIds = session.memberships.map((item) => item.workspace_id).join(',')
  const [state, setState] = useState<DraftState>({ kind: 'loading' })
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
  const [confirmedPreview, setConfirmedPreview] = useState(false)
  const [completionPending, setCompletionPending] = useState(false)
  const [exportPending, setExportPending] = useState(false)
  const [preparedDownload, setPreparedDownload] = useState<{
    url: string; filename: string; version: VersionRef
  } | null>(null)
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
  const [findingPending, setFindingPending] = useState(false)
  const [undoCount, setUndoCount] = useState(0)
  const [exactMatches, setExactMatches] = useState<{ findingId: string; result: ExactMatchesView } | null>(null)
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({})
  const [keepReason, setKeepReason] = useState<'false_match' | 'intended_disclosure'>('false_match')
  const [groupConfirmation, setGroupConfirmation] = useState<GroupConfirmation | null>(null)
  const [scanPending, setScanPending] = useState(false)
  const [settingsPending, setSettingsPending] = useState(false)
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const actionPending = pending || completionPending || exportPending || findingPending ||
    scanPending || settingsPending

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
      else document.querySelector<HTMLElement>('.review-panel-switch button[aria-pressed="true"]')?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [actionPending])

  useEffect(() => {
    if (groupConfirmation) groupConfirmRef.current?.focus()
  }, [groupConfirmation])

  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    Promise.all([
      getDraft(documentId, controller.signal),
      getScan(documentId, controller.signal),
      getFindings(documentId, controller.signal),
      getPreview(documentId, controller.signal),
    ]).then(([saved, scanResult, findingResult, previewResult]) => {
      if (controller.signal.aborted) return
      if (!sameVersion(saved.version, scanResult.version) ||
        !sameVersion(saved.version, findingResult.version) ||
        !sameVersion(saved.version, previewResult.version)) {
        setState({ kind: 'error', message: 'The review changed while loading. Retry to get one current version.' })
        return
      }
      setState({ kind: 'ready', saved })
      setText(saved.text)
      setEmailEnabled(saved.categories.includes('email'))
      setPhoneEnabled(saved.categories.includes('phone'))
      setPhoneRegion(saved.phone_region)
      setScan(scanResult)
      setFindings(findingResult)
      setPreview(previewResult)
      setPreviewError(null)
      setSummary(null)
      setConfirmedPreview(false)
      setSelection(null)
      setExactMatches(null)
      setUndoCount(0)
      setSelectedFindingId(null)
      setError(null)
      setConflict(false)
      if (saved.status === 'ready' || saved.status === 'exported') {
        getReviewSummary(documentId, controller.signal).then((result) => {
          if (!controller.signal.aborted && sameVersion(result.version, saved.version)) {
            setSummary(result)
          }
        }).catch(() => undefined)
      }
    }).catch(async (cause: unknown) => {
      if (controller.signal.aborted) return
      if (cause instanceof ApiRequestError && cause.status === 410) {
        const lists = await Promise.allSettled(workspaceIds.split(',').filter(Boolean).map(
          (id) => getWorkspaceDocuments(id, controller.signal),
        ))
        if (controller.signal.aborted) return
        const expired = lists.some((result) => result.status === 'fulfilled' && result.value.some(
          (item) => item.id === documentId && item.status === 'expired',
        ))
        if (expired) {
          setState({ kind: 'error', message: 'This document has expired. Its content can no longer be opened.', retryable: false })
          return
        }
      }
      setState({
        kind: 'error', message: messageFrom(cause),
        retryable: !(cause instanceof ApiRequestError && [404, 410].includes(cause.status)),
      })
    })
    return () => controller.abort()
  }, [documentId, attempt, workspaceIds])

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

  const dirty = state.kind === 'ready' && text !== state.saved.text
  const selectedCategories: Array<'email' | 'phone'> = [
    ...(emailEnabled ? ['email' as const] : []),
    ...(phoneEnabled ? ['phone' as const] : []),
  ]
  const settingsDirty = state.kind === 'ready' && (
    state.saved.categories.join(',') !== selectedCategories.join(',') ||
    state.saved.phone_region !== phoneRegion
  )
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  useEffect(() => {
    return () => {
      if (preparedDownload) URL.revokeObjectURL(preparedDownload.url)
    }
  }, [preparedDownload])

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
      setScan({
        version: saved.version, status: 'not_started', attempt_count: 0,
        match_count: null, failure_code: null, suggestions: [],
      })
      setFindings({ version: saved.version, findings: [], overlaps: [] })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setSelection(null)
      setExactMatches(null)
      setUndoCount(0)
      setSelectedFindingId(null)
      await refreshPreview(documentId, saved.version)
      setNotice('Draft saved as a new source revision. Review it again before export.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) {
        setConflict(true)
        setError('This draft changed in another session. Copy your edits or reload the latest saved version.')
      } else if (
        cause instanceof TypeError ||
        (cause instanceof ApiRequestError && [502, 504].includes(cause.status))
      ) {
        setError('The save could not be confirmed. Your edits remain in this tab. Retry when the connection returns, or copy them before reloading.')
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
    setScan(null)
    setFindings(null)
    setPreview(null)
    setPreviewError(null)
    setSummary(null)
    setConfirmedPreview(false)
    setPreparedDownload(null)
    setSelection(null)
    setExactMatches(null)
    setUndoCount(0)
    setSelectedFindingId(null)
    setAttempt((value) => value + 1)
  }

  async function scanDraft() {
    if (!documentId || state.kind !== 'ready') {
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
      const result = await startScan(documentId, state.saved.version, session.csrf_token)
      setScan(result)
      setUndoCount(0)
      if (result.status === 'completed') {
        setSummary(null)
        setConfirmedPreview(false)
        setPreparedDownload(null)
        setState({ kind: 'ready', saved: {
          ...state.saved, version: result.version, status: 'needs_review',
        } })
        setNotice(result.match_count === 0
          ? null : 'Suggestions are unresolved. Review every occurrence before export.')
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
      getScan(documentId).then(setScan).catch(() => undefined)
    } finally {
      setScanPending(false)
    }
  }

  async function saveSettings() {
    if (!documentId || state.kind !== 'ready' || dirty || !settingsDirty) return
    setSettingsPending(true)
    setError(null)
    try {
      const updated = await updateScanSettings(
        documentId, state.saved.version, selectedCategories, phoneRegion, session.csrf_token,
      )
      setState({ kind: 'ready', saved: {
        ...state.saved, version: updated.version, status: 'draft',
        categories: selectedCategories, phone_region: phoneRegion,
      } })
      setScan({ version: updated.version, status: 'not_started', attempt_count: 0,
        match_count: null, failure_code: null, suggestions: [] })
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
        getDraft(documentId), getScan(documentId), getFindings(documentId), getPreview(documentId),
      ])
      if (!sameVersion(latest.version, scanResult.version) ||
        !sameVersion(latest.version, findingResult.version) ||
        !sameVersion(latest.version, previewResult.version)) {
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

  const codePoints = state.kind === 'ready' ? Array.from(state.saved.text) : []
  const activeFindings = findings?.findings || []
  const selectionOverlaps = Boolean(selection && activeFindings.some(
    (item) => selection.start < item.span.end && item.span.start < selection.end,
  ))
  const visibleFindings = activeFindings.filter((item) =>
    (categoryFilter === 'all' || item.category === categoryFilter) &&
    (decisionFilter === 'all' || (decisionFilter === 'pending' ? item.action === null : item.action !== null)),
  )
  const pendingFindings = activeFindings.filter((item) => item.action === null)
  const currentReview = state.kind === 'ready' && !dirty && !settingsDirty && !conflict &&
    !pending && !settingsPending && !scanPending && !findingPending && !completionPending &&
    !exportPending && scan?.status === 'completed' &&
    sameScanVersion(scan.version, state.saved.version) &&
    findings !== null && sameVersion(findings.version, state.saved.version) &&
    findings.overlaps.length === 0 && pendingFindings.length === 0 &&
    preview?.status === 'complete' && preview.text !== null &&
    sameVersion(preview.version, state.saved.version)
  const canConfirm = state.kind === 'ready' && currentReview && state.saved.status === 'needs_review'
  const canExport = state.kind === 'ready' && currentReview &&
    (state.saved.status === 'ready' || state.saved.status === 'exported')
  const currentSummary = state.kind === 'ready' && summary &&
    sameVersion(summary.version, state.saved.version) ? summary : null
  const groupMembers = new Map<string, typeof activeFindings>()
  for (const item of activeFindings) {
    if (item.group_id) {
      groupMembers.set(item.group_id, [...(groupMembers.get(item.group_id) || []), item])
    }
  }

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
      const result = kind === 'add'
        ? await addManualFinding(
          documentId, state.saved.version, selection as SourceSpan,
          manualCategory, session.csrf_token,
        )
        : kind === 'revise'
          ? await reviseFinding(
            documentId, findingId as string, state.saved.version,
            selection as SourceSpan, manualCategory, session.csrf_token,
          )
          : await removeFinding(
            documentId, findingId as string, state.saved.version, session.csrf_token,
          )
      setFindings(result)
      if (selectedFindingId && !result.findings.some((item) => item.finding_id === selectedFindingId)) {
        setSelectedFindingId(null)
      }
      setState({ kind: 'ready', saved: {
        ...state.saved, version: result.version, status: 'needs_review',
      } })
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
      if (result.version.decision_version !== state.saved.version.decision_version) {
        setUndoCount((count) => Math.min(count + 1, 20))
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

  async function changeReview(
    operation: 'exact' | 'merge' | 'split' | 'decision', findingId: string,
    options?: { span?: SourceSpan; action?: 'label' | 'redact' | 'keep'; groupScope?: boolean },
  ) {
    if (!documentId || state.kind !== 'ready' || !findings || dirty || settingsDirty) return
    const item = findings.findings.find((candidate) => candidate.finding_id === findingId)
    if (!item) return
    const members = options?.groupScope && item.group_id
      ? findings.findings.filter((candidate) => candidate.group_id === item.group_id)
      : [item]
    setFindingPending(true)
    setError(null)
    setNotice(null)
    try {
      let result: FindingsView
      if (operation === 'exact' && options?.span) {
        result = await addExactMatch(documentId, findingId, state.saved.version,
          options.span, session.csrf_token)
      } else if (operation === 'merge' && mergeTargets[findingId]) {
        result = await mergeFindings(documentId, findingId, mergeTargets[findingId],
          state.saved.version, session.csrf_token)
      } else if (operation === 'split') {
        result = await splitFinding(documentId, findingId, state.saved.version, session.csrf_token)
      } else if (operation === 'decision' && options?.action) {
        result = await decideFindings(documentId, findingId, state.saved.version,
          options.action, options.action === 'keep' ? keepReason : null,
          Boolean(options.groupScope), members.map((member) => member.finding_id),
          session.csrf_token)
      } else return
      setFindings(result)
      if (operation === 'merge') {
        setMergeTargets((current) => ({ ...current, [findingId]: '' }))
      }
      setState({ kind: 'ready', saved: { ...state.saved, version: result.version,
        status: 'needs_review' } })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setExactMatches(null)
      setGroupConfirmation(null)
      await refreshPreview(documentId, result.version)
      if (result.version.decision_version !== state.saved.version.decision_version) {
        setUndoCount((count) => Math.min(count + 1, 20))
      }
      setNotice('Review change saved.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setFindingPending(false)
    }
  }

  async function undoReview() {
    if (!documentId || state.kind !== 'ready' || dirty || settingsDirty || undoCount === 0) return
    setFindingPending(true)
    setError(null)
    try {
      const result = await undoReviewEdit(documentId, state.saved.version, session.csrf_token)
      setFindings(result)
      setState({ kind: 'ready', saved: { ...state.saved, version: result.version,
        status: 'needs_review' } })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setUndoCount((count) => Math.max(0, count - 1))
      setExactMatches(null)
      setGroupConfirmation(null)
      await refreshPreview(documentId, result.version)
      setNotice('Last review edit undone. Review the current findings before completion.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setFindingPending(false)
    }
  }

  function confirmGroupDecision() {
    if (!groupConfirmation || state.kind !== 'ready' || !findings) return
    const item = findings.findings.find(
      (candidate) => candidate.finding_id === groupConfirmation.findingId,
    )
    const currentIds = item?.group_id
      ? findings.findings.filter((candidate) => candidate.group_id === item.group_id)
        .map((candidate) => candidate.finding_id)
      : []
    if (!sameVersion(groupConfirmation.version, state.saved.version) ||
      currentIds.length !== groupConfirmation.affectedIds.length ||
      !currentIds.every((id) => groupConfirmation.affectedIds.includes(id))) {
      setGroupConfirmation(null)
      setError('This group changed. Review its occurrences again before applying a decision.')
      return
    }
    const { findingId, action } = groupConfirmation
    setGroupConfirmation(null)
    lastFocusedRef.current = groupTriggerRef.current
    void changeReview('decision', findingId, { action, groupScope: true })
  }

  function cancelGroupDecision() {
    setGroupConfirmation(null)
    requestAnimationFrame(() => groupTriggerRef.current?.focus())
  }

  function locateFinding(findingId: string, target: 'source' | 'preview') {
    if (state.kind !== 'ready' || !findings || dirty || settingsDirty) return
    const item = findings.findings.find((row) => row.finding_id === findingId)
    if (!item) return
    setSelectedFindingId(findingId)
    setMobilePanel(target === 'source' ? 'original' : 'preview')
    if (target === 'source' && sourceRef.current) {
      const range = codePointRangeToUtf16(
        state.saved.text, item.span.start, item.span.end,
      )
      requestAnimationFrame(() => {
        sourceRef.current?.focus()
        sourceRef.current?.setSelectionRange(range.start, range.end)
        if (window.matchMedia('(min-width: 701px)').matches) {
          const panel = document.getElementById('review-findings-panel')
          const card = document.getElementById(`finding-${findingId}`)
          if (panel && card) {
            panel.scrollTop += card.getBoundingClientRect().top - panel.getBoundingClientRect().top - 80
          }
        }
      })
      return
    }
    const mapping = preview?.mappings.find((row) => row.finding_id === findingId)
    if (mapping && preview?.text && previewRef.current) {
      const range = codePointRangeToUtf16(
        preview.text, mapping.preview_span.start, mapping.preview_span.end,
      )
      requestAnimationFrame(() => {
        previewRef.current?.focus()
        previewRef.current?.setSelectionRange(range.start, range.end)
      })
    }
  }

  function nextUnresolved() {
    if (pendingFindings.length === 0) return
    const position = pendingFindings.findIndex((item) => item.finding_id === selectedFindingId)
    const next = pendingFindings[(position + 1) % pendingFindings.length]
    setCategoryFilter('all')
    setDecisionFilter('all')
    locateFinding(next.finding_id, 'source')
  }

  async function completeReview() {
    if (!documentId || state.kind !== 'ready' || !canConfirm || !confirmedPreview) return
    setCompletionPending(true)
    setError(null)
    setNotice(null)
    try {
      const completed = await confirmReview(documentId, state.saved.version, session.csrf_token)
      setState({ kind: 'ready', saved: { ...state.saved, status: completed.status } })
      setConfirmedPreview(false)
      setNotice('Review confirmed. The reviewed output is ready to copy or download.')
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
          documentId, payload.version, payload.completion_id, crypto.randomUUID(),
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
        setError('Text was copied, but its activity record could not be confirmed. Reload before trying again.')
      }
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setExportPending(false)
    }
  }

  async function downloadReviewedOutput() {
    if (!documentId || state.kind !== 'ready' || !canExport) return
    setExportPending(true)
    setError(null)
    setNotice(null)
    try {
      const file = await downloadReviewedTxt(
        documentId, state.saved.version, crypto.randomUUID(), session.csrf_token,
      )
      setState({ kind: 'ready', saved: { ...state.saved, status: 'exported' } })
      setPreparedDownload({
        url: URL.createObjectURL(file),
        filename: `reviewed-${documentId}.txt`,
        version: state.saved.version,
      })
      setNotice('Reviewed TXT generated. Use the save link to download it.')
      try {
        const result = await getReviewSummary(documentId)
        if (sameVersion(result.version, state.saved.version)) setSummary(result)
      } catch {
        setError('TXT generated, but the review summary could not be refreshed.')
      }
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setExportPending(false)
    }
  }

  return (
    <section className="review-page" aria-labelledby="review-title" onFocusCapture={(event) => {
      if (event.target instanceof HTMLElement) lastFocusedRef.current = event.target
    }}>
      <PageHeader title={state.kind === 'ready' ? state.saved.title || 'Untitled review' : 'Review workspace'}
        titleId="review-title" description="Inspect the original and reviewed output, then decide each finding."
        action={<Link to="/documents">Back to documents</Link>} />
      {state.kind === 'loading' && <p role="status">Loading the saved draft…</p>}
      {state.kind === 'error' && (
        <div role="alert">
          <p>{state.message}</p>
          {state.retryable !== false && <button type="button" onClick={reloadSaved}>Retry</button>}
        </div>
      )}
      {state.kind === 'ready' && (
        <>
          <div className="review-summary-strip" aria-label="Current review status">
            <StatusBadge status={state.saved.status} />
            {scan?.status === 'completed' || activeFindings.length > 0 ?
              <span>{pendingFindings.length > 0
                ? `${pendingFindings.length} ${pendingFindings.length === 1 ? 'finding' : 'findings'} still need a decision`
                : state.saved.status === 'ready' || state.saved.status === 'exported' ? 'Review confirmed'
                  : activeFindings.length === 0 ? 'No matches; review full text' : 'All findings have decisions'}</span>
              : <span>{scan?.status === 'scanning' ? 'Checking suggestions' : 'Suggestion scan not run'}</span>}
            <span>Expires {new Date(state.saved.expires_at).toLocaleString()}</span>
            <span>{dirty ? 'Unsaved source edits' : 'Source saved'}</span>
          </div>
          <details className="review-details"><summary>Review setup</summary>
            <p>Automatic suggestions: {state.saved.categories.join(', ') || 'none'}; phone region: {state.saved.phone_region}.</p>
            {state.saved.preset_id && (
              <p>Started with a Rules preset. Preferred action: {state.saved.preferred_action}. Later preset changes do not update this review.</p>
            )}
          </details>
          {error && !dirty && <p role="alert">{error}</p>}
          {notice && <p role="status">{notice}</p>}
          <div className="review-panel-switch" role="group" aria-label="Review views">
            {(['original', 'preview', 'findings'] as const).map((panel) => (
              <button key={panel} type="button" aria-pressed={mobilePanel === panel}
                aria-controls={`review-${panel}-panel`} onClick={() => setMobilePanel(panel)}>
                {panel === 'original' ? 'Original' : panel === 'preview' ? 'Reviewed output' : 'Findings'}
              </button>
            ))}
          </div>
          <div className="review-layout" data-mobile-panel={mobilePanel}>
          <section className="review-suggestions surface-panel" aria-labelledby="suggestions-heading">
            <h2 id="suggestions-heading">Automatic suggestions</h2>
            <p>Suggestions do not decide how text will be handled.</p>
            <button type="button" onClick={() => void scanDraft()}
              disabled={dirty || settingsDirty || pending || settingsPending || scanPending || conflict ||
                scan?.status === 'scanning' || scan?.status === 'completed'}>
              {scanPending ? 'Scanning…' : scan?.status === 'failed' ? 'Retry scan' : 'Find suggestions'}
            </button>{' '}
            <button type="button" onClick={() => void refreshScan()} disabled={dirty || scanPending}>
              Refresh scan status
            </button>
            {scan?.status === 'not_started' && <p>No scan has run for this source and settings.</p>}
            {scan?.status === 'scanning' && <p role="status">Scan in progress.</p>}
            {scan?.status === 'failed' && <p role="alert">Scan failed ({scan.failure_code}). Retry after checking the text or settings.</p>}
            {scan?.status === 'completed' && scan.match_count === 0 &&
              state.saved.status !== 'ready' && state.saved.status !== 'exported' &&
              <p>No suggestions found. The full text still needs review before export.</p>}
            {scan?.status === 'completed' && scan.match_count !== null && scan.match_count > 0 && (
              <details className="scan-explanations">
                <summary>{scan.match_count} suggestions found — view rule details</summary>
                <ol>
                {scan.suggestions.map((item) => (
                  <li key={item.finding_id}>
                    <strong>{item.category}</strong> at characters {item.span.start + 1}–{item.span.end}: {' '}
                    <code>{codePoints.slice(item.span.start, item.span.end).join('')}</code>. {' '}
                    {item.reason} Rule {item.rule_id} ({item.rule_version}). {' '}
                    {findings?.findings.find((finding) => finding.finding_id === item.finding_id)?.action || 'Pending review'}.
                  </li>
                ))}
                </ol>
              </details>
            )}
          </section>
          <div className="review-text-column">
          <form className="review-source surface-panel" id="review-original-panel" onSubmit={save}>
            <h2>Original text</h2>
            <label htmlFor="saved-source">Text to review</label>
            <textarea id="saved-source" className="source-editor" value={text} ref={sourceRef}
              aria-describedby={error && dirty ? 'source-save-error' : undefined}
              onMouseUp={captureSelection}
              onKeyUp={captureSelection}
              onChange={(event) => {
                setText(event.target.value)
                setSelection(null)
                setNotice(null)
                setConfirmedPreview(false)
                setPreparedDownload(null)
              }} />
            <p role="status">
              {Array.from(text).length.toLocaleString()} characters.
              {' '}{dirty ? 'Unsaved edits.' : 'Saved.'}
            </p>
            {error && dirty && <p id="source-save-error" role="alert">{error}</p>}
            <button type="submit" disabled={!dirty || pending || conflict}>
              {pending ? 'Saving…' : 'Save new revision'}
            </button>{' '}
            <button type="button" onClick={reloadSaved} disabled={pending}>
              {dirty ? 'Discard edits and reload saved' : 'Reload saved'}
            </button>
            {dirty && (
              <button type="button" onClick={() => void copyUnsaved()}>
                Copy unsaved edits
              </button>
            )}
          </form>
          <section className="review-preview surface-panel" id="review-preview-panel" aria-labelledby="preview-heading">
            <h2 id="preview-heading">Reviewed output preview</h2>
            {dirty || settingsDirty ? (
              <p>Save the source and suggestion settings to refresh this preview.</p>
            ) : preview?.status === 'conflict' ? (
              <p role="alert">Overlapping findings need correction or removal before a preview can be shown.</p>
            ) : preview && sameVersion(preview.version, state.saved.version) && preview.text !== null ? (
              <>
                <p role="status">{preview.status === 'incomplete'
                  ? `${preview.unresolved_finding_ids.length} ${preview.unresolved_finding_ids.length === 1 ? 'finding' : 'findings'} still need a decision. This preview is provisional.`
                  : state.saved.status === 'ready' || state.saved.status === 'exported'
                    ? 'This is the confirmed reviewed output.'
                  : scan?.status !== 'completed' && state.saved.categories.length > 0
                    ? 'All marked findings have decisions. Run the selected automatic scan, then inspect the full text.'
                    : 'All marked findings have decisions. Inspect the full text before final confirmation.'}</p>
                <label htmlFor="reviewed-preview">Reviewed output</label>
                <textarea id="reviewed-preview" className="source-editor" value={preview.text}
                  ref={previewRef} readOnly />
              </>
            ) : (
              <p role={previewError ? 'alert' : 'status'}>
                {previewError ? `Preview unavailable: ${previewError}` : 'Loading the current preview…'}
              </p>
            )}
            {previewError && !dirty && !settingsDirty && (
              <button type="button" onClick={() => void refreshPreview(documentId as string, state.saved.version)}>
                Retry preview
              </button>
            )}
          </section>
          </div>
          <section className="review-findings surface-panel" id="review-findings-panel" aria-labelledby="findings-heading">
            <h2 id="findings-heading">Current findings</h2>
            <p>Select an exact range in the saved text to add or correct a finding. Existing overlapping ranges must be corrected or removed first.</p>
            <p role="status">{activeFindings.length} active {activeFindings.length === 1 ? 'finding' : 'findings'}: {' '}
              {pendingFindings.length} pending, {' '}
              {activeFindings.filter((item) => item.action === 'label').length} labeled, {' '}
              {activeFindings.filter((item) => item.action === 'redact').length} redacted, {' '}
              {activeFindings.filter((item) => item.action === 'keep').length} kept.</p>
            <div className="finding-filter-grid"><div>
            <label htmlFor="finding-category-filter">Category filter</label>
            <select id="finding-category-filter" value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value as typeof categoryFilter)}>
              <option value="all">All categories</option>
              <option value="person">Person</option>
              <option value="organization">Organization</option>
              <option value="address">Address</option>
              <option value="identifier">Identifier</option>
              <option value="custom">Custom</option>
              <option value="email">Email</option>
              <option value="phone">Phone</option>
            </select></div><div>
            <label htmlFor="finding-decision-filter">Decision filter</label>
            <select id="finding-decision-filter" value={decisionFilter}
              onChange={(event) => setDecisionFilter(event.target.value as typeof decisionFilter)}>
              <option value="all">All decisions</option>
              <option value="pending">Pending</option>
              <option value="decided">Decided</option>
            </select></div></div>
            <button type="button" onClick={nextUnresolved}
              disabled={pendingFindings.length === 0 || dirty || settingsDirty}>
              Next unresolved
            </button>
            <button type="button" onClick={() => void undoReview()}
              disabled={undoCount === 0 || dirty || settingsDirty || findingPending || conflict}>
              Undo last review edit
            </button>
            {selection && (
              <p role="status">Selected characters {selection.start + 1}–{selection.end}: {' '}
                <code>{JSON.stringify(Array.from(text).slice(selection.start, selection.end).join(''))}</code></p>
            )}
            {selectionOverlaps && <p>This range overlaps a current finding. Correct or remove it first.</p>}
            <details className="manual-finding-controls" open={selection !== null}>
            <summary>Add a finding from selected text</summary>
            <label htmlFor="manual-category">Category</label>
            <select id="manual-category" value={manualCategory}
              onChange={(event) => setManualCategory(event.target.value as FindingCategory)}>
              <option value="person">Person</option>
              <option value="organization">Organization</option>
              <option value="address">Address</option>
              <option value="identifier">Identifier</option>
              <option value="custom">Custom</option>
              <option value="email">Email</option>
              <option value="phone">Phone</option>
            </select>{' '}
            <button type="button" onClick={() => void changeFinding('add')}
              disabled={!selection || selectionOverlaps || dirty || settingsDirty || findingPending || scanPending || conflict}>
              {findingPending ? 'Saving…' : 'Add selected finding'}
            </button>
            </details>
            <label htmlFor="keep-reason">Reason when keeping text</label>
            <select id="keep-reason" value={keepReason}
              onChange={(event) => setKeepReason(event.target.value as typeof keepReason)}>
              <option value="false_match">False match</option>
              <option value="intended_disclosure">Intended disclosure</option>
            </select>
            {findings && findings.overlaps.length > 0 && (
              <p role="alert">{findings.overlaps.length} overlapping range(s) need correction or removal.</p>
            )}
            {findings?.findings.length === 0 && <p>No active findings for this source revision.</p>}
            {activeFindings.length > 0 && visibleFindings.length === 0 &&
              <p>No findings match these filters.</p>}
            {groupMembers.size > 0 && (
              <div aria-label="Entity groups">
                <h3>Linked occurrences</h3>
                {Array.from(groupMembers, ([groupId, members]) => (
                  <details key={groupId}>
                    <summary>{members[0].label} — {members.length} {members.length === 1 ? 'occurrence' : 'occurrences'}</summary>
                    <ul>{members.map((member) => (
                      <li key={member.finding_id}>
                        Characters {member.span.start + 1}–{member.span.end}: {' '}
                        {member.action || 'pending'}
                      </li>
                    ))}</ul>
                  </details>
                ))}
              </div>
            )}
            {findings && findings.findings.length > 0 && (
              <ol className="finding-list">
                {visibleFindings.map((item) => (
                  <li key={item.finding_id} id={`finding-${item.finding_id}`}
                    aria-current={selectedFindingId === item.finding_id ? 'true' : undefined}>
                    <div className="finding-header"><strong>{item.category}</strong>
                      <span className={`finding-state${item.action ? ' is-decided' : ''}`}>
                        {item.action ?? 'Pending review'}
                      </span></div>
                    <p className="finding-excerpt"><code>{JSON.stringify(
                      codePoints.slice(item.span.start, item.span.end).join(''),
                    )}</code></p>
                    <p className="finding-meta">Characters {item.span.start + 1}–{item.span.end} · {' '}
                      {item.origin === 'automatic' ? 'Automatic suggestion' : 'Manual finding'}
                      {item.keep_reason ? ` · ${item.keep_reason.replace('_', ' ')}` : ''}
                      {item.label ? ` · ${item.label}` : ''}</p>
                    <div className="finding-decision-actions" role="group"
                      aria-label={`Decision for ${item.category} at characters ${item.span.start + 1}–${item.span.end}`}>
                      {(['label', 'redact', 'keep'] as const).map((action) => (
                        <button className={`finding-action finding-action--${action}`}
                          key={action} type="button" aria-pressed={item.action === action}
                          onClick={() => void changeReview('decision', item.finding_id, { action })}
                          disabled={dirty || settingsDirty || findingPending || conflict}>
                          {action === 'keep' ? 'Keep' : action === 'label' ? 'Label' : 'Redact'}
                          {action === state.saved.preferred_action ? ' (preferred)' : ''}
                        </button>
                      ))}
                    </div>
                    <details className="finding-more"><summary>More finding actions</summary>
                    <div className="finding-extra-actions">
                    <button type="button" onClick={() => void changeFinding('revise', item.finding_id)}
                      disabled={!selection || activeFindings.some((other) =>
                        other.finding_id !== item.finding_id &&
                        selection.start < other.span.end && other.span.start < selection.end,
                      ) || dirty || settingsDirty || findingPending || scanPending || conflict}>
                      Use selected range
                    </button>{' '}
                    <button type="button" onClick={() => void changeFinding('remove', item.finding_id)}
                      disabled={dirty || settingsDirty || findingPending || scanPending || conflict}>
                      Remove finding
                    </button>{' '}
                    {item.group_id && findings.findings.filter(
                      (candidate) => candidate.group_id === item.group_id,
                    ).length > 1 && (
                      <>
                        <button type="button" onClick={() => void changeReview('split', item.finding_id)}
                          disabled={dirty || settingsDirty || findingPending || conflict}>
                          Review separately
                        </button>{' '}
                        {(['label', 'redact', 'keep'] as const).map((action) => (
                          <button key={action} type="button"
                            onClick={(event) => {
                              const members = findings.findings.filter(
                                (candidate) => candidate.group_id === item.group_id,
                              )
                              groupTriggerRef.current = event.currentTarget
                              setGroupConfirmation({
                                findingId: item.finding_id,
                                action,
                                affectedIds: members.map((member) => member.finding_id),
                                spans: members.map((member) => member.span),
                                version: state.saved.version,
                              })
                            }}
                            disabled={dirty || settingsDirty || findingPending || conflict}>
                            {action === 'label' ? 'Label' : action === 'redact' ? 'Redact' : 'Keep'} all linked
                          </button>
                        ))}
                        {groupConfirmation?.findingId === item.finding_id && (
                          <div role="group" aria-label="Confirm group decision">
                            <p>Apply {groupConfirmation.action} to {groupConfirmation.affectedIds.length} occurrences
                              at {groupConfirmation.spans.map(
                                (span) => `${span.start + 1}–${span.end}`,
                              ).join(', ')}?</p>
                            <button ref={groupConfirmRef} type="button" onClick={confirmGroupDecision}
                              disabled={dirty || settingsDirty || findingPending || conflict}>Apply to all linked</button>{' '}
                            <button type="button" onClick={cancelGroupDecision}>Cancel</button>
                          </div>
                        )}
                      </>
                    )}
                    <label htmlFor={`merge-${item.finding_id}`}>Link with another occurrence</label>{' '}
                    <select id={`merge-${item.finding_id}`} value={mergeTargets[item.finding_id] || ''}
                      onChange={(event) => setMergeTargets((current) => ({
                        ...current, [item.finding_id]: event.target.value,
                      }))}>
                      <option value="">Choose occurrence</option>
                      {findings.findings.filter((candidate) =>
                        candidate.finding_id !== item.finding_id && candidate.category === item.category &&
                        (!item.group_id || candidate.group_id !== item.group_id),
                      ).map((candidate) => <option key={candidate.finding_id} value={candidate.finding_id}>
                        {candidate.span.start + 1}–{candidate.span.end}
                      </option>)}
                    </select>{' '}
                    <button type="button" onClick={() => void changeReview('merge', item.finding_id)}
                      disabled={!mergeTargets[item.finding_id] || dirty || settingsDirty || findingPending || conflict}>
                      Link occurrences
                    </button>{' '}
                    <button type="button" onClick={() => void showExactMatches(item.finding_id)}
                      disabled={dirty || settingsDirty || findingPending || conflict}>
                      Find other identical text
                    </button>{' '}
                    <button type="button" onClick={() => locateFinding(item.finding_id, 'source')}
                      disabled={dirty || settingsDirty}>
                      Locate original
                    </button>{' '}
                    {preview?.mappings.some((mapping) => mapping.finding_id === item.finding_id) && (
                      <button type="button" onClick={() => locateFinding(item.finding_id, 'preview')}
                        disabled={dirty || settingsDirty || preview.status === 'conflict'}>
                        Locate preview
                      </button>
                    )}
                    {exactMatches?.findingId === item.finding_id && (
                      <div>
                        <p>{exactMatches.result.spans.length} unmarked exact matches
                          {exactMatches.result.truncated ? ' (first 100 shown)' : ''}.</p>
                        {exactMatches.result.spans.map((span) => (
                          <button key={span.start} type="button"
                            onClick={() => void changeReview('exact', item.finding_id, { span })}
                            disabled={findingPending || conflict}>
                            Mark characters {span.start + 1}–{span.end}
                          </button>
                        ))}
                      </div>
                    )}
                    </div>
                    </details>
                  </li>
                ))}
              </ol>
            )}
          </section>
          <section className="review-completion surface-panel" aria-labelledby="completion-heading">
            <h2 id="completion-heading">Finish review and export</h2>
            <p>Read the entire reviewed output above, including passages without findings. It may still identify someone through context.</p>
            {state.saved.status === 'needs_review' && (
              <>
                <label><input type="checkbox" checked={confirmedPreview}
                  disabled={!canConfirm}
                  onChange={(event) => setConfirmedPreview(event.target.checked)} />
                  I reviewed the full output and confirm this version.</label>{' '}
                <button type="button" onClick={() => void completeReview()}
                  disabled={!canConfirm || !confirmedPreview}>
                  {completionPending ? 'Confirming…' : 'Confirm review'}
                </button>
              </>
            )}
            {state.saved.status !== 'ready' && state.saved.status !== 'exported' && !canConfirm && (
              <p role="status">Complete the current scan, resolve all findings and overlaps, and save any edits before confirmation.</p>
            )}
            {(state.saved.status === 'ready' || state.saved.status === 'exported') && (
              <p role="status">This version and its review decisions are confirmed.</p>
            )}
            <div>
              <button type="button" onClick={() => void copyReviewedOutput()} disabled={!canExport}>
                {exportPending ? 'Preparing output…' : 'Copy reviewed text'}
              </button>{' '}
              <button type="button" onClick={() => void downloadReviewedOutput()} disabled={!canExport}>
                Generate reviewed TXT
              </button>
            </div>
            {preparedDownload && canExport &&
              sameVersion(preparedDownload.version, state.saved.version) && (
                <p><a href={preparedDownload.url} download={preparedDownload.filename}>
                  Save reviewed TXT
                </a></p>
              )}
            {currentSummary && !dirty && !settingsDirty && (
              <div aria-label="Review summary">
                <h3>Review summary</h3>
                <p>{currentSummary.finding_count === 0
                  ? 'No findings were marked.'
                  : `${currentSummary.finding_count} ${currentSummary.finding_count === 1 ? 'finding' : 'findings'} reviewed.`}</p>
                <p>Categories: {Object.entries(currentSummary.counts_by_category)
                  .map(([category, count]) => `${category} ${count}`).join(', ') || 'none'}.</p>
                <p>Decisions: {Object.entries(currentSummary.counts_by_action)
                  .map(([action, count]) => `${action} ${count}`).join(', ') || 'none'}.
                  {' '}Kept: {currentSummary.counts_by_action.keep || 0}.</p>
                <p>Confirmed: {new Date(currentSummary.confirmed_at).toLocaleString()}.
                  {' '}Last output generated: {currentSummary.last_output_generated_at
                    ? new Date(currentSummary.last_output_generated_at).toLocaleString()
                    : 'never'}.</p>
              </div>
            )}
          </section>
          <section className="review-settings surface-panel" aria-labelledby="suggestion-settings-heading">
            <h2 id="suggestion-settings-heading">Suggestion settings</h2>
            <p>Changing these settings starts a new review. Save text edits first.</p>
            <label><input type="checkbox" checked={emailEnabled}
              onChange={(event) => {
                setEmailEnabled(event.target.checked)
                setConfirmedPreview(false)
                setPreparedDownload(null)
              }} />Email addresses</label>{' '}
            <label><input type="checkbox" checked={phoneEnabled}
              onChange={(event) => {
                setPhoneEnabled(event.target.checked)
                setConfirmedPreview(false)
                setPreparedDownload(null)
              }} />Phone numbers</label>{' '}
            <label htmlFor="scan-phone-region">Phone region</label>{' '}
            <select id="scan-phone-region" value={phoneRegion}
              onChange={(event) => {
                setPhoneRegion(event.target.value)
                setConfirmedPreview(false)
                setPreparedDownload(null)
              }}>
              <option value="PH">Philippines</option>
              <option value="US">United States</option>
              <option value="GB">United Kingdom</option>
              <option value="CA">Canada</option>
              <option value="AU">Australia</option>
              <option value="IN">India</option>
            </select>{' '}
            <button type="button" onClick={() => void saveSettings()}
              disabled={!settingsDirty || dirty || pending || settingsPending || scanPending || conflict}>
              {settingsPending ? 'Saving settings…' : 'Save suggestion settings'}
            </button>
          </section>

          </div>

        </>
      )}
    </section>
  )
}
