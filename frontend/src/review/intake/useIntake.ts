import { importPreview } from '../../imports/api'
import { extras } from '../../detection/categories'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useProtectedDraft } from '../../recovery/useProtectedDraft'
import {
  createPastedDraft,
  getIntakeDefaults,
  getWorkspacePresets,
  type IntakeDefaultsView,
  type PresetView,
  type SessionView,
  type FindingCategory,
} from '../../api/client'

type Defaults =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; value: IntakeDefaultsView; presets: PresetView[] }

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

export function useIntake(session: SessionView) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const allowNavigationRef = useRef(false)
  const [initialWorkspace] = useState(() => session.memberships.find((item) => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? '')
  const [workspaceId, setWorkspaceId] = useState(initialWorkspace)
  const [defaults, setDefaults] = useState<Defaults>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState<'paste' | 'file'>('paste')
  const [source, setSource] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileText, setFileText] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileNotes, setFileNotes] = useState<string[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [phoneEnabled, setPhoneEnabled] = useState(true)
  const [extraCategories, setExtraCategories] = useState<FindingCategory[]>([])
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [language, setLanguage] = useState('en')
  const [presetId, setPresetId] = useState('')
  const [retentionDays, setRetentionDays] = useState(7)
  const [submitting, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.all([
      getIntakeDefaults(workspaceId, controller.signal),
      getWorkspacePresets(workspaceId, controller.signal),
    ])
      .then(([value, presets]) => {
        if (controller.signal.aborted) return
        setDefaults({ kind: 'ready', value, presets })
        setRetentionDays(value.content_retention_days)
        const initial = presets.find((preset) => preset.is_default)
        setPresetId(initial?.id ?? '')
        setEmailEnabled(initial?.categories.includes('email') ?? true)
        setPhoneEnabled(initial?.categories.includes('phone') ?? true)
        setExtraCategories(extras(initial?.categories ?? []))
        setPhoneRegion(initial?.phone_region ?? 'PH')
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setDefaults({ kind: 'error', message: messageFrom(cause) })
      })
    return () => controller.abort()
  }, [workspaceId, attempt])

  const fileAttempt = useRef(0)

  async function chooseFile(selected: File | null, selectionCount = 1) {
    const request = ++fileAttempt.current
    setFile(selected)
    setFileText('')
    setFileError(null)
    setFileNotes([])
    setFileLoading(false)
    if (!selected) return
    if (selectionCount !== 1) {
      setFileError('Choose exactly one file per review.')
      return
    }
    setFileLoading(true)
    if (!/\.(txt|pdf|docx)$/i.test(selected.name)) {
      setFileError('Choose one UTF-8 TXT, PDF or Word DOCX file.')
      setFileLoading(false)
      return
    }
    if (selected.size > (/\.txt$/i.test(selected.name) ? 1_048_576 : 8_388_608)) {
      setFileError('TXT supports 1 MiB; PDF and DOCX support 8 MiB.')
      setFileLoading(false)
      return
    }
    try {
      const result = await importPreview(workspaceId, selected, session.csrf_token)
      if (fileAttempt.current !== request) return
      setFileText(result.text)
      setFileNotes(result.notes)
    } catch (cause) {
      if (fileAttempt.current === request) setFileError(messageFrom(cause))
    } finally {
      if (fileAttempt.current === request) setFileLoading(false)
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!readyToSave) return
    if (mode === 'file' && (!file || fileError || fileLoading || !fileText.trim())) return
    setPending(true)
    setError(null)
    const categories = [...(emailEnabled ? ['email'] : []), ...(phoneEnabled ? ['phone'] : []), ...extraCategories]
    try {
      const saved = await createPastedDraft({ workspace_id: workspaceId,
        source: mode === 'paste' ? source : fileText, title: title.trim() || null,
        categories: categories as FindingCategory[], phone_region: phoneRegion, language,
        retention_days: retentionDays, preset_id: presetId || null,
      }, session.csrf_token)
      await recovery.clear().catch(() => undefined)
      allowNavigationRef.current = true
      navigate(`/documents/${saved.version.document_id}/edit`)
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setPending(false)
    }
  }

  const previewText = mode === 'paste' ? source : fileText
  const characters = Array.from(previewText).length
  const bytes = new TextEncoder().encode(previewText).length
  const overLimit = characters > 100_000 || bytes > 1_048_576
  const initialPreset =
    defaults.kind === 'ready' ? defaults.presets.find((preset) => preset.is_default) : undefined
  const intakeDirty =
    source.length > 0 ||
    file !== null ||
    title.trim().length > 0 ||
    workspaceId !== initialWorkspace || language !== 'en' ||
    (defaults.kind === 'ready' &&
      (presetId !== (initialPreset?.id ?? '') ||
        emailEnabled !== (initialPreset?.categories.includes('email') ?? true) ||
        phoneEnabled !== (initialPreset?.categories.includes('phone') ?? true) ||
        extraCategories.slice().sort().join(',') !== extras(initialPreset?.categories ?? []).sort().join(',') ||
        phoneRegion !== (initialPreset?.phone_region ?? 'PH') ||
        retentionDays !== defaults.value.content_retention_days))

  const recovery = useProtectedDraft({
    scope: defaults.kind === 'ready' ? {
      userId: session.user_id, workspaceId, documentId: null,
    } : null,
    csrf: session.csrf_token,
    dirty: intakeDirty,
    paused: submitting || overLimit || fileLoading || Boolean(fileError),
    payload: defaults.kind === 'ready' ? {
      source: previewText, title, categories: [
        ...(emailEnabled ? ['email' as const] : []), ...(phoneEnabled ? ['phone' as const] : []), ...extraCategories,
      ], phone_region: phoneRegion, language, retention_days: retentionDays,
      preset_id: presetId || null, base_version: null,
    } : null,
    onRestore: (view) => {
      setSource(view.payload.source)
      setTitle(view.payload.title ?? '')
      setMode('paste')
      setFile(null)
      setFileText('')
      setFileError(null)
      setEmailEnabled(view.payload.categories.includes('email'))
      setPhoneEnabled(view.payload.categories.includes('phone'))
      setExtraCategories(extras(view.payload.categories))
      setPhoneRegion(view.payload.phone_region)
      setLanguage(view.payload.language ?? 'en')
      setPresetId(defaults.kind === 'ready' && defaults.presets.some((item) => item.id === view.payload.preset_id)
        ? view.payload.preset_id ?? '' : '')
      setRetentionDays(defaults.kind === 'ready'
        ? Math.min(view.payload.retention_days, defaults.value.content_retention_days)
        : view.payload.retention_days)
    },
  })
  const pending = submitting || defaults.kind === 'loading' || recovery.loading
  const readyToSave = defaults.kind === 'ready' && !pending && !overLimit &&
    (mode === 'paste' ? source.trim().length > 0
      : file !== null && !fileLoading && fileError === null && fileText.trim().length > 0)

  return {
    recovery,
    workspaceId,
    setWorkspaceId,
    defaults,
    setDefaults,
    setAttempt,
    mode,
    setMode,
    source,
    setSource,
    file,
    fileText,
    fileLoading,
    fileError,
    fileNotes,
    chooseFile,
    title,
    setTitle,
    extraCategories,
    setExtraCategories,
    emailEnabled,
    setEmailEnabled,
    phoneEnabled,
    setPhoneEnabled,
    phoneRegion,
    setPhoneRegion,
    language,
    setLanguage,
    presetId,
    setPresetId,
    retentionDays,
    setRetentionDays,
    pending,
    error,
    save,
    characters,
    bytes,
    overLimit,
    readyToSave,
    submitting,
    intakeDirty,
    allowNavigationRef,
  }
}

export type IntakeController = ReturnType<typeof useIntake>
