import type { Dispatch, SetStateAction } from 'react'
import {
  ApiConflictError, decideColumn, getFindings, updateColumnRules, updateCsvSettings,
  updateWorkspacePreset, type ColumnDecisionRequest, type ColumnRule, type CsvDelimiter,
  type CsvSettingsView, type FindingsView, type PresetView, type ScanView, type VersionRef,
} from '../api/client'
import { messageFrom, sameVersion, type DraftState } from './reviewState'

type Update<T> = Dispatch<SetStateAction<T>>

export function createReviewCsvActions({
  state, blocked, canManagePresets, csrf, resetReview, refreshPreview, setState,
  setSettingsPending, setFindingPending, setError, setNotice, setConflict, setScan, setFindings,
}: {
  state: DraftState; blocked: boolean; canManagePresets: boolean; csrf: string;
  resetReview: () => void; refreshPreview: (id: string, expected: VersionRef) => Promise<void>;
  setState: Update<DraftState>; setSettingsPending: Update<boolean>; setFindingPending: Update<boolean>;
  setError: Update<string | null>; setNotice: Update<string | null>; setConflict: Update<boolean>;
  setScan: Update<ScanView | null>; setFindings: Update<FindingsView | null>;
}) {
  async function changeSettings(request: () => Promise<CsvSettingsView>): Promise<boolean> {
    if (blocked || state.kind !== 'ready' || !state.saved.csv || !state.saved.can_edit) return false
    setSettingsPending(true); setError(null); setNotice(null)
    try {
      const result = await request()
      if (sameVersion(result.version, state.saved.version)) {
        setNotice('CSV settings already match the saved review.')
        return true
      }
      const { version, ...csv } = result
      setState({ kind: 'ready', saved: { ...state.saved, version, csv, status: 'draft' } })
      resetReview()
      setScan({ version, status: 'not_started', attempt_count: 0, match_count: null,
        dropped_suggestions: 0, failure_code: null, suggestions: [] })
      setFindings(null)
      try {
        const findings = await getFindings(version.document_id)
        if (!sameVersion(findings.version, version)) throw new Error('The review changed. Reload the saved version.')
        setFindings(findings)
      } catch {
        setConflict(true)
        setError('CSV settings saved, but findings could not be refreshed. Reload the saved review.')
      }
      await refreshPreview(version.document_id, version)
      setNotice('CSV settings saved. Run a fresh scan and review every finding before export.')
      return true
    } catch (cause) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
      return false
    } finally { setSettingsPending(false) }
  }

  function saveCsvFormat(delimiter: CsvDelimiter, hasHeader: boolean) {
    if (state.kind !== 'ready') return Promise.resolve(false)
    return changeSettings(() => updateCsvSettings(state.saved.version.document_id,
      state.saved.version.settings_version, delimiter, hasHeader, csrf))
  }
  function saveColumnRules(rules: ColumnRule[]) {
    if (state.kind !== 'ready') return Promise.resolve(false)
    return changeSettings(() => updateColumnRules(state.saved.version.document_id,
      state.saved.version.settings_version, rules, csrf))
  }

  async function applyColumnDecision(column: number, body: ColumnDecisionRequest): Promise<boolean> {
    if (blocked || state.kind !== 'ready' || !state.saved.csv || !state.saved.can_edit) return false
    if (!sameVersion(body.expected, state.saved.version)) {
      setError('The review changed. Inspect the affected column findings again.')
      return false
    }
    setFindingPending(true); setError(null); setNotice(null)
    try {
      const result = await decideColumn(state.saved.version.document_id, column, body, csrf)
      setFindings(result)
      setState({ kind: 'ready', saved: { ...state.saved, version: result.version, status: 'needs_review' } })
      resetReview()
      await refreshPreview(result.version.document_id, result.version)
      setNotice(`Decision saved for ${body.affected_finding_ids.length} findings in column ${column + 1}.`)
      return true
    } catch (cause) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
      return false
    } finally { setFindingPending(false) }
  }

  async function saveColumnPreset(preset: PresetView): Promise<boolean> {
    if (blocked || !canManagePresets || state.kind !== 'ready' || !state.saved.csv?.has_header) return false
    const csv = state.saved.csv
    const rules = csv.rules.map((rule) => ({ ...rule, header: csv.headers[rule.column] }))
    if (rules.some((rule) => Array.from(rule.header).length > 1000)) {
      setError('Preset column names must contain at most 1,000 characters.')
      return false
    }
    setSettingsPending(true); setError(null); setNotice(null)
    try {
      await updateWorkspacePreset(state.saved.workspace_id, preset.id, {
        name: preset.name, categories: preset.categories, phone_region: preset.phone_region,
        preferred_action: preset.preferred_action, is_default: preset.is_default,
        category_defaults: preset.category_defaults, column_rules: rules,
      }, preset.version, csrf)
      setNotice('Column rules saved to the preset. New CSV imports match them by header name.')
      return true
    } catch (cause) { setError(messageFrom(cause)); return false }
    finally { setSettingsPending(false) }
  }
  return { saveCsvFormat, saveColumnRules, applyColumnDecision, saveColumnPreset }
}
