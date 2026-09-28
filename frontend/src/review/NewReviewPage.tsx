import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createFileDraft, createPastedDraft, getIntakeDefaults, getWorkspacePresets,
  type IntakeDefaultsView, type PresetView, type SessionView,
} from '../api/client'
import { PageHeader } from '../ui/PageHeader'

type Defaults =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; value: IntakeDefaultsView; presets: PresetView[] }

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

function formattedExpiry(now: string, days: number): string {
  const expiry = new Date(new Date(now).getTime() + days * 86_400_000)
  return expiry.toLocaleString()
}

export function NewReviewPage({ session }: { session: SessionView }) {
  const navigate = useNavigate()
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [defaults, setDefaults] = useState<Defaults>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState<'paste' | 'file'>('paste')
  const [source, setSource] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileText, setFileText] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [presetId, setPresetId] = useState('')
  const [retentionDays, setRetentionDays] = useState(7)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.all([
      getIntakeDefaults(workspaceId, controller.signal),
      getWorkspacePresets(workspaceId, controller.signal),
    ]).then(([value, presets]) => {
      if (controller.signal.aborted) return
      setDefaults({ kind: 'ready', value, presets })
      setRetentionDays(value.content_retention_days)
      const initial = presets.find((preset) => preset.is_default)
      setPresetId(initial?.id ?? '')
      setEmailEnabled(initial?.categories.includes('email') ?? true)
      setPhoneEnabled(initial?.categories.includes('phone') ?? true)
      setPhoneRegion(initial?.phone_region ?? 'PH')
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setDefaults({ kind: 'error', message: messageFrom(cause) })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.currentTarget.files?.[0] ?? null
    setFile(selected)
    setFileText('')
    setFileError(null)
    if (!selected) return
    setFileLoading(true)
    if (!selected.name.toLowerCase().endsWith('.txt')) {
      setFileError('Choose a UTF-8 .txt file.')
      setFileLoading(false)
      return
    }
    if (selected.size > 1_048_576) {
      setFileError('File exceeds the 1 MiB limit.')
      setFileLoading(false)
      return
    }
    try {
      const bytes = await selected.arrayBuffer()
      const decoded = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
      setFileText(decoded)
      if (!decoded.trim()) setFileError('The file has no text to review.')
    } catch {
      setFileError('File must be encoded as UTF-8 text.')
    } finally {
      setFileLoading(false)
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (defaults.kind !== 'ready') return
    if (mode === 'file' && (!file || fileError || fileLoading || !fileText.trim())) return
    setPending(true)
    setError(null)
    const categories = [
      ...(emailEnabled ? ['email'] : []),
      ...(phoneEnabled ? ['phone'] : []),
    ]
    try {
      const saved = mode === 'paste'
        ? await createPastedDraft({
          workspace_id: workspaceId,
          source,
          title: title.trim() || null,
          categories: categories as Array<'email' | 'phone'>,
          phone_region: phoneRegion,
          retention_days: retentionDays,
          preset_id: presetId || null,
        }, session.csrf_token)
        : await createFileDraft(
          workspaceId, file as File, title.trim(), categories, phoneRegion,
          retentionDays, session.csrf_token, presetId || undefined,
        )
      navigate(`/documents/${saved.version.document_id}/edit`)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setPending(false)
    }
  }

  const previewText = mode === 'paste' ? source : fileText
  const characters = Array.from(previewText).length
  const bytes = mode === 'file' ? (file?.size ?? 0) : new TextEncoder().encode(previewText).length
  const readyToSave = defaults.kind === 'ready' && !pending &&
    (mode === 'paste' ? source.trim().length > 0 :
      file !== null && !fileLoading && fileError === null && fileText.trim().length > 0)

  return (
    <section aria-labelledby="new-review-title">
      <PageHeader title="New review" titleId="new-review-title"
        description="Save a private draft before finding and reviewing possible sensitive information." />
      {error && <p role="alert">{error}</p>}
      {defaults.kind === 'loading' && <p role="status">Loading workspace limits…</p>}
      {defaults.kind === 'error' && (
        <div role="alert"><p>{defaults.message}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button>
        </div>
      )}
      <form onSubmit={save}>
        {session.memberships.length > 1 && (
          <>
            <label htmlFor="intake-workspace">Workspace</label>{' '}
            <select id="intake-workspace" value={workspaceId}
              onChange={(event) => {
                setDefaults({ kind: 'loading' })
                setWorkspaceId(event.target.value)
              }}>
              {session.memberships.map((item) => (
                <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_id}</option>
              ))}
            </select>
          </>
        )}
        <fieldset>
          <legend>Source</legend>
          <label><input type="radio" name="source-mode" checked={mode === 'paste'}
            onChange={() => setMode('paste')} />Paste text</label>{' '}
          <label><input type="radio" name="source-mode" checked={mode === 'file'}
            onChange={() => setMode('file')} />UTF-8 TXT file</label>
          {mode === 'paste' ? (
            <>
              <label htmlFor="source-text" className="block-label">Text to review</label>
              <textarea id="source-text" className="source-editor" value={source}
                onChange={(event) => setSource(event.target.value)} required />
            </>
          ) : (
            <>
              <label htmlFor="source-file" className="block-label">Choose one .txt file</label>
              <input id="source-file" type="file" accept=".txt,text/plain"
                onChange={(event) => void chooseFile(event)} required />
              {fileLoading && <p role="status">Reading file text…</p>}
              {fileError && <p role="alert">{fileError}</p>}
              {fileText && (
                <>
                  <label htmlFor="file-preview" className="block-label">File text to review</label>
                  <textarea id="file-preview" className="source-editor" value={fileText} readOnly />
                </>
              )}
            </>
          )}
          <p role="status">{characters.toLocaleString()} characters, {bytes.toLocaleString()} UTF-8 bytes. Maximum: 100,000 characters and 1 MiB.</p>
        </fieldset>
        <label htmlFor="draft-title">Optional title</label>{' '}
        <input id="draft-title" type="text" maxLength={200} value={title}
          onChange={(event) => setTitle(event.target.value)} />
        <p>The uploaded filename is never used as the document title or storage name.</p>
        <fieldset>
          <legend>Automatic suggestions</legend>
          {defaults.kind === 'ready' && defaults.presets.length > 0 && (
            <>
              <label htmlFor="intake-preset">Rules preset</label>{' '}
              <select id="intake-preset" value={presetId} onChange={(event) => {
                const id = event.target.value
                setPresetId(id)
                const preset = defaults.presets.find((item) => item.id === id)
                if (preset) {
                  setEmailEnabled(preset.categories.includes('email'))
                  setPhoneEnabled(preset.categories.includes('phone'))
                  setPhoneRegion(preset.phone_region)
                }
              }}>
                <option value="">Custom settings</option>
                {defaults.presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}{preset.is_default ? ' — workspace default' : ''} (v{preset.version})
                  </option>
                ))}
              </select>
              {presetId && <p>The chosen preset sets categories, phone region, and a preferred review action. You will still decide each finding.</p>}
            </>
          )}
          <label><input type="checkbox" checked={emailEnabled}
            onChange={(event) => setEmailEnabled(event.target.checked)} disabled={!!presetId} />Email addresses</label>{' '}
          <label><input type="checkbox" checked={phoneEnabled}
            onChange={(event) => setPhoneEnabled(event.target.checked)} disabled={!!presetId} />Phone numbers</label>{' '}
          <label htmlFor="phone-region">Phone region</label>{' '}
          <select id="phone-region" value={phoneRegion}
            onChange={(event) => setPhoneRegion(event.target.value)} disabled={!!presetId}>
            <option value="PH">Philippines</option>
            <option value="US">United States</option>
            <option value="GB">United Kingdom</option>
            <option value="CA">Canada</option>
            <option value="AU">Australia</option>
            <option value="IN">India</option>
          </select>
        </fieldset>
        {defaults.kind === 'ready' && (
          <>
            <label htmlFor="retention-days">Keep draft for</label>{' '}
            <select id="retention-days" value={retentionDays}
              onChange={(event) => setRetentionDays(Number(event.target.value))}>
              {Array.from({ length: defaults.value.content_retention_days }, (_item, index) => index + 1)
                .map((days) => <option key={days} value={days}>{days} day{days > 1 ? 's' : ''}</option>)}
            </select>
            <p>Expected expiry: approximately {formattedExpiry(defaults.value.current_time, retentionDays)}. The saved expiry is set by the server.</p>
          </>
        )}
        <button type="submit" disabled={!readyToSave}>{pending ? 'Saving…' : 'Save draft'}</button>
      </form>
    </section>
  )
}
