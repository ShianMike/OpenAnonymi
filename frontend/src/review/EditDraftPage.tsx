import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import {
  ApiConflictError, getDraft, getScan, saveDraftSource, startScan, updateScanSettings,
  type ScanView, type SessionView, type SourceView,
} from '../api/client'

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
  const [scanPending, setScanPending] = useState(false)
  const [settingsPending, setSettingsPending] = useState(false)
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [phoneRegion, setPhoneRegion] = useState('PH')

  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    Promise.all([
      getDraft(documentId, controller.signal), getScan(documentId, controller.signal),
    ]).then(([saved, scanResult]) => {
      if (controller.signal.aborted) return
      setState({ kind: 'ready', saved })
      setText(saved.text)
      setEmailEnabled(saved.categories.includes('email'))
      setPhoneEnabled(saved.categories.includes('phone'))
      setPhoneRegion(saved.phone_region)
      setScan(scanResult)
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
      setError(null)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    }
  }

  const codePoints = state.kind === 'ready' ? Array.from(state.saved.text) : []

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
              onChange={(event) => {
                setText(event.target.value)
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
                    {item.reason} Rule {item.rule_id} ({item.rule_version}). Pending review.
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
