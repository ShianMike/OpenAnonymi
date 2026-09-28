import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import {
  ApiConflictError, addExactMatch, addManualFinding, decideFindings, getDraft, getExactMatches,
  getFindings, getScan, mergeFindings, removeFinding, reviseFinding, saveDraftSource,
  splitFinding, startScan, undoReviewEdit, updateScanSettings,
  type ExactMatchesView, type FindingCategory, type FindingsView, type ScanView, type SessionView,
  type SourceSpan, type SourceView,
} from '../api/client'
import { utf16OffsetToCodePoint } from './offsets'

type DraftState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; saved: SourceView }

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

export function EditDraftPage({ session }: { session: SessionView }) {
  const { documentId } = useParams<{ documentId: string }>()
  const [state, setState] = useState<DraftState>({ kind: 'loading' })
  const [text, setText] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [scan, setScan] = useState<ScanView | null>(null)
  const [findings, setFindings] = useState<FindingsView | null>(null)
  const [selection, setSelection] = useState<SourceSpan | null>(null)
  const [manualCategory, setManualCategory] = useState<FindingCategory>('person')
  const [findingPending, setFindingPending] = useState(false)
  const [undoCount, setUndoCount] = useState(0)
  const [exactMatches, setExactMatches] = useState<{ findingId: string; result: ExactMatchesView } | null>(null)
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({})
  const [keepReason, setKeepReason] = useState<'false_match' | 'intended_disclosure'>('false_match')
  const [scanPending, setScanPending] = useState(false)
  const [settingsPending, setSettingsPending] = useState(false)
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [phoneRegion, setPhoneRegion] = useState('PH')

  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    Promise.all([
      getDraft(documentId, controller.signal),
      getScan(documentId, controller.signal),
      getFindings(documentId, controller.signal),
    ]).then(([saved, scanResult, findingResult]) => {
      if (controller.signal.aborted) return
      setState({ kind: 'ready', saved })
      setText(saved.text)
      setEmailEnabled(saved.categories.includes('email'))
      setPhoneEnabled(saved.categories.includes('phone'))
      setPhoneRegion(saved.phone_region)
      setScan(scanResult)
      setFindings(findingResult)
      setSelection(null)
      setExactMatches(null)
      setUndoCount(0)
      setError(null)
      setConflict(false)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setState({ kind: 'error', message: messageFrom(cause) })
    })
    return () => controller.abort()
  }, [documentId, attempt])

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
      setSelection(null)
      setExactMatches(null)
      setUndoCount(0)
      setNotice('Draft saved as a new source revision. Review it again before export.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) {
        setConflict(true)
        setError('This draft changed in another session. Copy your edits or reload the latest saved version.')
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
    setSelection(null)
    setExactMatches(null)
    setUndoCount(0)
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
      setFindings(await getFindings(documentId))
      setUndoCount(0)
      if (result.status === 'completed') {
        setState({ kind: 'ready', saved: {
          ...state.saved, version: result.version, status: 'needs_review',
        } })
        setNotice(result.match_count === 0
          ? 'No suggestions were found. Review the full text before export.'
          : 'Suggestions are unresolved. Review every occurrence before export.')
      } else {
        setNotice('A scan is in progress. Refresh its status shortly.')
      }
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
      await updateScanSettings(
        documentId, state.saved.version, selectedCategories, phoneRegion, session.csrf_token,
      )
      const latest = await getDraft(documentId)
      setState({ kind: 'ready', saved: latest })
      setScan(await getScan(documentId))
      setFindings(await getFindings(documentId))
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
      const latest = await getDraft(documentId)
      setState({ kind: 'ready', saved: latest })
      setScan(await getScan(documentId))
      setFindings(await getFindings(documentId))
      setUndoCount(0)
      setError(null)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    }
  }

  const codePoints = state.kind === 'ready' ? Array.from(state.saved.text) : []

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
      setScan(await getScan(documentId))
      setState({ kind: 'ready', saved: {
        ...state.saved, version: result.version, status: 'needs_review',
      } })
      setSelection(null)
      setExactMatches(null)
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
      setState({ kind: 'ready', saved: { ...state.saved, version: result.version,
        status: 'needs_review' } })
      setExactMatches(null)
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
      setUndoCount((count) => Math.max(0, count - 1))
      setExactMatches(null)
      setNotice('Last review edit undone. Review the current findings before completion.')
    } catch (cause: unknown) {
      if (cause instanceof ApiConflictError) setConflict(true)
      setError(messageFrom(cause))
    } finally {
      setFindingPending(false)
    }
  }

  return (
    <section>
      <h1>Saved draft</h1>
      {state.kind === 'loading' && <p role="status">Loading the saved draft…</p>}
      {state.kind === 'error' && (
        <div role="alert">
          <p>{state.message}</p>
          <button type="button" onClick={reloadSaved}>Retry</button>
        </div>
      )}
      {state.kind === 'ready' && (
        <>
          <p>{state.saved.title || `Review ${state.saved.version.document_id}`}</p>
          <p>Status: {state.saved.status}. Expires: {new Date(state.saved.expires_at).toLocaleString()}.</p>
          <p>Suggestions: {state.saved.categories.join(', ') || 'none'}; phone region: {state.saved.phone_region}.</p>
          <p>Source revision: {state.saved.version.source_revision_id}</p>
          {error && <p role="alert">{error}</p>}
          {notice && <p role="status">{notice}</p>}
          <form onSubmit={save}>
            <label htmlFor="saved-source">Text to review</label>
            <textarea id="saved-source" className="source-editor" value={text}
              onMouseUp={captureSelection}
              onKeyUp={captureSelection}
              onChange={(event) => {
                setText(event.target.value)
                setSelection(null)
                setNotice(null)
              }} />
            <p role="status">
              {Array.from(text).length.toLocaleString()} characters.
              {' '}{dirty ? 'Unsaved edits.' : 'Saved.'}
            </p>
            <button type="submit" disabled={!dirty || pending || conflict}>
              {pending ? 'Saving…' : 'Save new revision'}
            </button>{' '}
            <button type="button" onClick={reloadSaved} disabled={pending}>
              {dirty ? 'Discard edits and reload saved' : 'Reload saved'}
            </button>
          </form>
          {conflict && (
            <button type="button" onClick={() => void copyUnsaved()}>
              Copy unsaved edits
            </button>
          )}
          <section aria-labelledby="suggestion-settings-heading">
            <h2 id="suggestion-settings-heading">Suggestion settings</h2>
            <p>Changing these settings starts a new review. Save text edits first.</p>
            <label><input type="checkbox" checked={emailEnabled}
              onChange={(event) => setEmailEnabled(event.target.checked)} />Email addresses</label>{' '}
            <label><input type="checkbox" checked={phoneEnabled}
              onChange={(event) => setPhoneEnabled(event.target.checked)} />Phone numbers</label>{' '}
            <label htmlFor="scan-phone-region">Phone region</label>{' '}
            <select id="scan-phone-region" value={phoneRegion}
              onChange={(event) => setPhoneRegion(event.target.value)}>
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
          <section aria-labelledby="suggestions-heading">
            <h2 id="suggestions-heading">Automatic suggestions</h2>
            <p>Suggestions do not decide how text will be handled.</p>
            <button type="button" onClick={() => void scanDraft()}
              disabled={dirty || settingsDirty || pending || settingsPending || scanPending || conflict ||
                scan?.status === 'scanning'}>
              {scanPending ? 'Scanning…' : scan?.status === 'failed' ? 'Retry scan' : 'Find suggestions'}
            </button>{' '}
            <button type="button" onClick={() => void refreshScan()} disabled={dirty || scanPending}>
              Refresh scan status
            </button>
            {scan?.status === 'not_started' && <p>No scan has run for this source and settings.</p>}
            {scan?.status === 'scanning' && <p role="status">Scan in progress.</p>}
            {scan?.status === 'failed' && <p role="alert">Scan failed ({scan.failure_code}). Retry after checking the text or settings.</p>}
            {scan?.status === 'completed' && scan.match_count === 0 &&
              <p>No suggestions found. The full text still needs review before export.</p>}
            {scan?.status === 'completed' && scan.match_count !== null && scan.match_count > 0 && (
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
            )}
          </section>
          <section aria-labelledby="findings-heading">
            <h2 id="findings-heading">Current findings</h2>
            <p>Select an exact range in the saved text to add or correct a finding. Existing overlapping ranges must be corrected or removed first.</p>
            <button type="button" onClick={() => void undoReview()}
              disabled={undoCount === 0 || dirty || settingsDirty || findingPending || conflict}>
              Undo last review edit
            </button>
            {selection && (
              <p role="status">Selected characters {selection.start + 1}–{selection.end}: {' '}
                <code>{JSON.stringify(Array.from(text).slice(selection.start, selection.end).join(''))}</code></p>
            )}
            <label htmlFor="manual-category">Category</label>{' '}
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
              disabled={!selection || dirty || settingsDirty || findingPending || scanPending || conflict}>
              {findingPending ? 'Saving…' : 'Add selected finding'}
            </button>
            <label htmlFor="keep-reason">Keep reason</label>{' '}
            <select id="keep-reason" value={keepReason}
              onChange={(event) => setKeepReason(event.target.value as typeof keepReason)}>
              <option value="false_match">False match</option>
              <option value="intended_disclosure">Intended disclosure</option>
            </select>
            {findings && findings.overlaps.length > 0 && (
              <p role="alert">{findings.overlaps.length} overlapping range(s) need correction or removal.</p>
            )}
            {findings?.findings.length === 0 && <p>No active findings for this source revision.</p>}
            {findings && findings.findings.length > 0 && (
              <ol>
                {findings.findings.map((item) => (
                  <li key={item.finding_id}>
                    <strong>{item.category}</strong> at characters {item.span.start + 1}–{item.span.end}: {' '}
                    <code>{JSON.stringify(codePoints.slice(item.span.start, item.span.end).join(''))}</code>. {' '}
                    {item.origin === 'automatic' ? 'Automatic suggestion' : 'Manual finding'}; {' '}
                    {item.action ?? 'pending review'}{item.keep_reason ? ` (${item.keep_reason.replace('_', ' ')})` : ''}{item.label ? `; group ${item.label}` : ''}. {' '}
                    <button type="button" onClick={() => void changeFinding('revise', item.finding_id)}
                      disabled={!selection || dirty || settingsDirty || findingPending || scanPending || conflict}>
                      Correct to selection
                    </button>{' '}
                    <button type="button" onClick={() => void changeFinding('remove', item.finding_id)}
                      disabled={dirty || settingsDirty || findingPending || scanPending || conflict}>
                      Remove finding
                    </button>{' '}
                    {(['label', 'redact', 'keep'] as const).map((action) => (
                      <button key={action} type="button"
                        onClick={() => void changeReview('decision', item.finding_id, { action })}
                        disabled={dirty || settingsDirty || findingPending || conflict}>
                        {action === 'keep' ? 'Keep' : action === 'label' ? 'Label' : 'Redact'} this
                      </button>
                    ))}{' '}
                    {item.group_id && findings.findings.filter(
                      (candidate) => candidate.group_id === item.group_id,
                    ).length > 1 && (
                      <>
                        <button type="button" onClick={() => void changeReview('split', item.finding_id)}
                          disabled={dirty || settingsDirty || findingPending || conflict}>
                          Split from group
                        </button>{' '}
                        {(['label', 'redact', 'keep'] as const).map((action) => (
                          <button key={action} type="button"
                            onClick={() => {
                              const members = findings.findings.filter(
                                (candidate) => candidate.group_id === item.group_id,
                              )
                              if (window.confirm(`Apply ${action} to ${members.length} occurrences at ${members.map(
                                (member) => `${member.span.start + 1}–${member.span.end}`,
                              ).join(', ')}?`)) {
                                void changeReview('decision', item.finding_id, { action, groupScope: true })
                              }
                            }}
                            disabled={dirty || settingsDirty || findingPending || conflict}>
                            {action} group
                          </button>
                        ))}
                      </>
                    )}
                    <label htmlFor={`merge-${item.finding_id}`}>Merge with</label>{' '}
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
                      Merge groups
                    </button>{' '}
                    <button type="button" onClick={() => void showExactMatches(item.finding_id)}
                      disabled={dirty || settingsDirty || findingPending || conflict}>
                      Find exact matches
                    </button>
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
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </section>
  )
}
