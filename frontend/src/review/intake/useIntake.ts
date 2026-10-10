import { importPreview, type ImportPreview } from '../../imports/api'
import { defaultDetectionCategories, extras } from '../../detection/categories'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useProtectedDraft } from '../../recovery/useProtectedDraft'
import { findIntakePreset, workspacePresetId } from '../../workspace/rules/builtInPresets'
import {
  createPastedDraft,
  createFileDraft,
  getIntakeDefaults,
  getWorkspacePresets,
  startScan,
  type IntakeDefaultsView,
  type PresetView,
  type SessionView,
  type FindingCategory,
  type CsvInfo,
  type CsvDelimiter,
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
  const location = useLocation()
  const [params] = useSearchParams()
  const allowNavigationRef = useRef(false)
  const [initialWorkspace] = useState(() => session.memberships.find((item) => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? '')
  const [workspaceId, storeWorkspaceId] = useState(initialWorkspace)
  const [requestedPreset] = useState(params.get('preset') ?? '')
  const [presetNavigationKey] = useState(location.key)
  const [defaults, setDefaults] = useState<Defaults>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState<'paste' | 'file'>('paste')
  const [source, setSource] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileText, setFileText] = useState('')
  const [fileOriginalText, setFileOriginalText] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileNotes, setFileNotes] = useState<string[]>([])
  const [filePagePreviews, setFilePagePreviews] = useState<NonNullable<ImportPreview['page_previews']>>([])
  const [filePages, setFilePages] = useState<number | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [csvDelimiter, setCsvDelimiter] = useState<CsvDelimiter | 'auto'>('auto')
  const [csvHeader, setCsvHeader] = useState<'auto' | 'true' | 'false'>('auto')
  const [csvPreview, setCsvPreview] = useState<CsvInfo | null>(null)
  const [title, setTitle] = useState('')
  const [emailEnabled, setEmailEnabled] = useState(defaultDetectionCategories.includes('email'))
  const [phoneEnabled, setPhoneEnabled] = useState(defaultDetectionCategories.includes('phone'))
  const [extraCategories, setExtraCategories] = useState<FindingCategory[]>(extras(defaultDetectionCategories))
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [language, setLanguage] = useState('en')
  const [presetId, setPresetId] = useState('')
  const [retentionDays, setRetentionDays] = useState(7)
  const [submitting, setPending] = useState(false)
  const [findingSuggestions, setFindingSuggestions] = useState(false)
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
        const initial = (workspaceId === initialWorkspace ? findIntakePreset(requestedPreset, presets) : undefined)
          ?? presets.find((preset) => preset.is_default)
        setPresetId(initial?.id ?? '')
        const categories = initial?.categories ?? defaultDetectionCategories
        setEmailEnabled(categories.includes('email'))
        setPhoneEnabled(categories.includes('phone'))
        setExtraCategories(extras(categories))
        setPhoneRegion(initial?.phone_region ?? 'PH')
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setDefaults({ kind: 'error', message: messageFrom(cause) })
      })
    return () => controller.abort()
  }, [workspaceId, initialWorkspace, requestedPreset, attempt])

  const fileAttempt = useRef(0)

  async function chooseFile(selected: File | null, selectionCount = 1, delimiter = csvDelimiter, header = csvHeader) {
    const request = ++fileAttempt.current
    setFile(selected)
    setFileText('')
    setFileOriginalText('')
    setFileError(null)
    setFileNotes([])
    setFilePagePreviews([])
    setFilePages(null)
    setCsvPreview(null)
    setFileLoading(false)
    if (!selected) return
    if (selectionCount !== 1) {
      setFileError('Choose exactly one file per review.')
      return
    }
    setFileLoading(true)
    if (!/\.(txt|md|csv|pdf|docx|png|jpe?g|tiff?|webp)$/i.test(selected.name)) {
      setFileError('Choose TXT, Markdown, CSV, PDF, DOCX, PNG, JPEG, TIFF or WebP.')
      setFileLoading(false)
      return
    }
    if (selected.size > (/\.(txt|md|csv)$/i.test(selected.name) ? 1_048_576 : 8_388_608)) {
      setFileError('TXT, Markdown and CSV support 1 MiB; documents and images support 8 MiB.')
      setFileLoading(false)
      return
    }
    try {
      const result = await importPreview(workspaceId, selected, session.csrf_token, delimiter, header)
      if (fileAttempt.current !== request) return
      setFileText(result.text)
      setFileOriginalText(result.text)
      setFileNotes(result.notes)
      setFilePagePreviews(result.page_previews ?? [])
      setFilePages(result.pages)
      setCsvPreview(result.csv ?? null)
    } catch (cause) {
      if (fileAttempt.current === request) setFileError(messageFrom(cause))
    } finally {
      if (fileAttempt.current === request) setFileLoading(false)
    }
  }

  function resetFilePreview() {
    // A result from the old workspace must not populate the new workspace's draft.
    ++fileAttempt.current
    setFile(null); setFileText(''); setFileOriginalText(''); setFileNotes([])
    setFilePagePreviews([]); setFilePages(null)
    setCsvPreview(null); setFileError(null); setFileLoading(false)
  }

  function setWorkspaceId(value: string) {
    if (value === workspaceId) return
    if (fileLoading) resetFilePreview()
    storeWorkspaceId(value)
  }

  useEffect(() => () => { ++fileAttempt.current }, [])

  function changeCsvFormat(delimiter: typeof csvDelimiter, header: typeof csvHeader) {
    setCsvDelimiter(delimiter); setCsvHeader(header)
    if (file) void chooseFile(file, 1, delimiter, header)
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!readyToSave) return
    if (mode === 'file' && (!file || fileError || fileLoading || !fileText.trim())) return
    setPending(true)
    setError(null)
    const findSuggestions = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') !== 'save'
    const categories = [...(emailEnabled ? ['email'] : []), ...(phoneEnabled ? ['phone'] : []), ...extraCategories]
    try {
      const saved = mode === 'file' && file ? await createFileDraft(workspaceId, file, title.trim(), categories, phoneRegion, retentionDays, session.csrf_token, workspacePresetId(presetId) ?? undefined, language, csvDelimiter, csvHeader, fileText) : await createPastedDraft({ workspace_id: workspaceId,
        source: mode === 'paste' ? source : fileText, title: title.trim() || null,
        categories: categories as FindingCategory[], phone_region: phoneRegion, language,
        retention_days: retentionDays, preset_id: workspacePresetId(presetId),
      }, session.csrf_token)
      await recovery.clear().catch(() => undefined)
      let scanError: string | null = null
      if (findSuggestions) {
        setFindingSuggestions(true)
        try {
          await startScan(saved.version.document_id, saved.version, session.csrf_token)
        } catch (cause: unknown) {
          // The draft already exists; open it for retry rather than create a duplicate.
          scanError = `Your draft was saved, but suggestions could not start. ${messageFrom(cause)}`
        }
      }
      allowNavigationRef.current = true
      navigate(`/documents/${saved.version.document_id}/edit`, { state: scanError ? { scanError } : null })
    } catch (cause: unknown) {
      setError(messageFrom(cause))
    } finally {
      setPending(false)
      setFindingSuggestions(false)
    }
  }

  const previewText = mode === 'paste' ? source : fileText
  const characters = Array.from(previewText).length
  const bytes = new TextEncoder().encode(previewText).length
  const overLimit = characters > 100_000 || bytes > 1_048_576
  const initialPreset =
    defaults.kind === 'ready' ? (workspaceId === initialWorkspace ? findIntakePreset(requestedPreset, defaults.presets) : undefined)
      ?? defaults.presets.find((preset) => preset.is_default) : undefined
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
    startKey: requestedPreset && workspaceId === initialWorkspace && defaults.kind === 'ready'
      && findIntakePreset(requestedPreset, defaults.presets) ? `${presetNavigationKey}:${requestedPreset}` : undefined,
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
      preset_id: workspacePresetId(presetId), base_version: null,
    } : null,
    onRestore: (view) => {
      setSource(view.payload.source)
      setTitle(view.payload.title ?? '')
      setMode('paste')
      resetFilePreview()
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
    setFileText,
    fileEdited: fileText !== fileOriginalText,
    hasFilePreview: fileOriginalText.length > 0,
    fileLoading,
    fileError,
    fileNotes,
    filePagePreviews,
    filePages,
    csvDelimiter,
    csvHeader,
    csvPreview,
    changeCsvFormat,
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
    findingSuggestions,
    intakeDirty,
    allowNavigationRef,
  }
}

export type IntakeController = ReturnType<typeof useIntake>
