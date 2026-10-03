import type { Dispatch, SetStateAction } from 'react'
import { ApiConflictError, addExactMatch, decideFindings, mergeFindings, splitFinding, undoReviewEdit,
  refreshCategoryDefaults, getDraft, type FindingsView, type ExactMatchesView, type PreviewView,
  type ReviewSummaryView, type SourceSpan, type StyleChoice, type VersionRef } from '../api/client'
import { messageFrom, sameVersion, type DraftState, type GroupConfirmation } from './reviewState'
import { preferredChoice } from './useStyleControls'

type Update<T> = Dispatch<SetStateAction<T>>
export type DecisionOptions = { span?: SourceSpan; action?: 'label' | 'redact' | 'keep';
  groupScope?: boolean; keepReason?: 'false_match' | 'intended_disclosure'; choice?: StyleChoice }

export function createReviewDecisionActions({ documentId, state, findings, preview, dirty, settingsDirty,
  actionPending, conflict, mergeTargets, keepReason, csrf, undoCount, groupConfirmation,
  refreshPreview, setFindingPending, setError, setNotice, setFindings,
  setMergeTargets, setState, setSummary, setConfirmedPreview, setPreparedDownload, setExactMatches,
  setGroupConfirmation, setConflict }: {
  documentId: string | undefined; state: DraftState; findings: FindingsView | null; preview: PreviewView | null;
  dirty: boolean; settingsDirty: boolean; actionPending: boolean; conflict: boolean; csrf: string;
  mergeTargets: Record<string, string>; keepReason: 'false_match' | 'intended_disclosure'; undoCount: number;
  groupConfirmation: GroupConfirmation | null;
  refreshPreview: (id: string, version: VersionRef) => Promise<void>;
  setFindingPending: Update<boolean>; setError: Update<string | null>; setNotice: Update<string | null>;
  setFindings: Update<FindingsView | null>; setMergeTargets: Update<Record<string, string>>;
  setState: Update<DraftState>; setSummary: Update<ReviewSummaryView | null>; setConfirmedPreview: Update<boolean>;
  setPreparedDownload: Update<{ url: string; filename: string; version: VersionRef } | null>;
  setExactMatches: Update<{findingId: string; result: ExactMatchesView} | null>;
  setGroupConfirmation: Update<GroupConfirmation | null>; setConflict: Update<boolean>;
}) {
  async function changeReview(
    operation: 'exact' | 'merge' | 'split' | 'decision',
    findingId: string,
    options?: DecisionOptions,
  ) {
    if (
      !documentId ||
      state.kind !== 'ready' ||
      !findings ||
      dirty ||
      settingsDirty ||
      actionPending ||
      conflict
    )
      return
    if (!sameVersion(findings.version, state.saved.version)) {
      setConflict(true)
      setError('The findings changed. Reload the saved review before deciding.')
      return
    }
    const item = findings.findings.find((candidate) => candidate.finding_id === findingId)
    if (!item) return
    const members =
      options?.groupScope && item.group_id
        ? findings.findings.filter((candidate) => candidate.group_id === item.group_id)
        : [item]
    setFindingPending(true)
    setError(null)
    setNotice(null)
    try {
      let result: FindingsView
      if (operation === 'exact' && options?.span) {
        result = await addExactMatch(
          documentId,
          findingId,
          state.saved.version,
          options.span,
          csrf,
        )
      } else if (operation === 'merge' && mergeTargets[findingId]) {
        result = await mergeFindings(
          documentId,
          findingId,
          mergeTargets[findingId],
          state.saved.version,
          csrf,
        )
      } else if (operation === 'split') {
        result = await splitFinding(documentId, findingId, state.saved.version, csrf)
      } else if (operation === 'decision' && options?.action) {
        result = await decideFindings(
          documentId,
          findingId,
          state.saved.version,
          options.action,
          options.action === 'keep' ? options.keepReason ?? keepReason : null,
          Boolean(options.groupScope),
          members.map((member) => member.finding_id),
          csrf,
          options.choice ?? preferredChoice(state.saved, item, options.action, preview),
        )
      } else return
      setFindings(result)
      if (operation === 'merge') {
        setMergeTargets((current) => ({ ...current, [findingId]: '' }))
      }
      setState({
        kind: 'ready',
        saved: { ...state.saved, version: result.version, status: 'needs_review' },
      })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
      setExactMatches(null)
      setGroupConfirmation(null)
      await refreshPreview(documentId, result.version)
      setNotice('Review change saved.')
      return true
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
      const result = await undoReviewEdit(documentId, state.saved.version, csrf)
      setFindings(result)
      setState({
        kind: 'ready',
        saved: { ...state.saved, version: result.version, status: 'needs_review' },
      })
      setSummary(null)
      setConfirmedPreview(false)
      setPreparedDownload(null)
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
      ? findings.findings
          .filter((candidate) => candidate.group_id === item.group_id)
          .map((candidate) => candidate.finding_id)
      : []
    if (
      !sameVersion(groupConfirmation.version, state.saved.version) ||
      currentIds.length !== groupConfirmation.affectedIds.length ||
      !currentIds.every((id) => groupConfirmation.affectedIds.includes(id))
    ) {
      setGroupConfirmation(null)
      setError('This group changed. Review its occurrences again before applying a decision.')
      return
    }
    const { findingId, action, choice } = groupConfirmation
    setGroupConfirmation(null)
    void changeReview('decision', findingId, { action, choice, groupScope: true })
  }

  function cancelGroupDecision() {
    setGroupConfirmation(null)
  }

  async function useLatestDefaults() {
    if (!documentId || state.kind !== 'ready' || !state.saved.can_edit || !state.saved.preset_id ||
        actionPending || dirty || settingsDirty || conflict) return
    setFindingPending(true); setError(null)
    try {
      const result = await refreshCategoryDefaults(documentId, state.saved.version.decision_version, csrf)
      setFindings(result)
      setSummary(null); setConfirmedPreview(false); setPreparedDownload(null)
      setExactMatches(null); setGroupConfirmation(null)
      setState({ kind: 'ready', saved: { ...state.saved, version: result.version, status: 'needs_review' } })
      const latest = await getDraft(documentId)
      if (!sameVersion(latest.version, result.version)) {
        setConflict(true); setError('The review changed while loading defaults. Reload the saved review.'); return
      }
      setState({ kind: 'ready', saved: latest })
      await refreshPreview(documentId, result.version)
      setNotice('Latest preset defaults loaded. Existing decisions are unchanged; confirm the output again.')
    } catch (cause) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally { setFindingPending(false) }
  }
  return { changeReview, undoReview, confirmGroupDecision, cancelGroupDecision, useLatestDefaults }
}
