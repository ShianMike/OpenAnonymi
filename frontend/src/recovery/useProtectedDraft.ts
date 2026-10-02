import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../api/client'
import { deleteRecovery, getRecovery, listRecovery, saveRecovery,
  type RecoveryMetadata, type RecoveryPayload, type RecoveryView } from './api'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function workingId(key: string) {
  try {
    const existing = sessionStorage.getItem(key)
    if (existing && UUID.test(existing)) return existing
  } catch { /* Storage is optional; encrypted server recovery still works. */ }
  const id = crypto.randomUUID()
  rememberId(key, id)
  return id
}

function rememberId(key: string, id: string) {
  try { sessionStorage.setItem(key, id) } catch { /* No content is stored here. */ }
}

type Scope = { userId: string; workspaceId: string; documentId: string | null }
type Runtime = { key: string; id: string; version: number; initialized: boolean;
  disposed: boolean; clearing: boolean; forkOnRetry: boolean; operation: Promise<void> | null;
  confirmedHash: string }

export function useProtectedDraft({ scope, csrf, payload, dirty, paused = false, onRestore }: {
  scope: Scope | null
  csrf: string
  payload: RecoveryPayload | null
  dirty: boolean
  paused?: boolean
  onRestore: (view: RecoveryView) => void
}) {
  const key = scope ? `openanonymi.working-id.${scope.userId}.${scope.workspaceId}.${scope.documentId ?? 'intake'}` : ''
  const [attempt, setAttempt] = useState(0)
  const [phase, setPhase] = useState<'loading' | 'idle' | 'saving' | 'saved' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [savedHash, setSavedHash] = useState('')
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [recoveredAt, setRecoveredAt] = useState<string | null>(null)
  const [copies, setCopies] = useState<RecoveryMetadata[]>([])
  const runtime = useRef<Runtime | null>(null)
  const latest = useRef({ scope, payload, dirty, paused, csrf, onRestore })
  latest.current = { scope, payload, dirty, paused, csrf, onRestore }
  const hash = payload ? JSON.stringify(payload) : ''

  useEffect(() => {
    if (!key || !scope) return
    const controller = new AbortController()
    const run: Runtime = { key, id: workingId(key), version: 0, initialized: false,
      disposed: false, clearing: false, forkOnRetry: false, operation: null, confirmedHash: '' }
    runtime.current = run
    setPhase('loading')
    setError(null)
    setSavedHash('')
    setRecoveredAt(null)
    setSavedAt(null)
    async function load() {
      try {
        const available = await listRecovery(scope!.workspaceId, scope!.documentId, controller.signal)
        if (controller.signal.aborted) return
        setCopies(available)
        let fresh = false
        try { fresh = sessionStorage.getItem(`${key}.fresh`) === 'true' } catch { /* Optional metadata. */ }
        const chosen = available.find((item) => item.id === run.id) ?? (fresh ? undefined : available[0])
        if (chosen?.id !== run.id) {
          run.id = crypto.randomUUID()
          rememberId(key, run.id)
        }
        if (chosen) {
          const view = await getRecovery(scope!.workspaceId, chosen.id, controller.signal)
          if (controller.signal.aborted) return
          // A different tab's copy is restored into a new slot. Keep its original
          // slot intact so simultaneous tabs can never overwrite each other's text.
          if (chosen.id === run.id) {
            run.version = view.version
            run.confirmedHash = JSON.stringify(view.payload)
            setSavedHash(JSON.stringify(view.payload))
            setSavedAt(view.updated_at)
          }
          latest.current.onRestore(view)
          setRecoveredAt(view.updated_at)
        }
        run.initialized = true
        setPhase(chosen?.id === run.id ? 'saved' : 'idle')
      } catch (cause) {
        if (controller.signal.aborted) return
        setError(cause instanceof Error ? cause.message : 'Working draft recovery is unavailable.')
        setPhase('error')
      }
    }
    void load()
    return () => { controller.abort(); run.disposed = true }
  // The scope key contains every identity/scope value; callbacks and current text
  // live in latest so typing does not restart recovery or discard the write queue.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt])

  const saveNow = useCallback(async () => {
    const run = runtime.current
    const current = latest.current
    if (!run || run.key !== key || !run.initialized || run.disposed || run.clearing ||
        !current.scope || !current.payload || !current.dirty || current.paused) return
    if (run.operation) return run.operation
    const captured = current.payload
    const capturedHash = JSON.stringify(captured)
    if (capturedHash === run.confirmedHash) return
    if (run.forkOnRetry) {
      run.id = crypto.randomUUID()
      run.version = 0
      run.forkOnRetry = false
      rememberId(key, run.id)
    }
    setPhase('saving')
    setError(null)
    const operation = (async () => {
      try {
        const result = await saveRecovery(current.scope!.workspaceId, run.id, run.version,
          current.scope!.documentId, captured, current.csrf)
        run.version = result.version
        run.confirmedHash = capturedHash
        try { sessionStorage.removeItem(`${key}.fresh`) } catch { /* No content is stored. */ }
        if (run.disposed) return
        setSavedHash(capturedHash)
        setSavedAt(result.updated_at)
        setPhase('saved')
        setCopies((rows) => [result, ...rows.filter((item) => item.id !== result.id)])
      } catch (cause) {
        if (run.disposed) return
        run.forkOnRetry = cause instanceof ApiRequestError && cause.code === 'recovery_conflict'
        setPhase('error')
        setError(cause instanceof Error ? cause.message : 'Autosave could not be confirmed. Your edits remain here.')
      } finally { run.operation = null }
    })()
    run.operation = operation
    return operation
  }, [key])

  useEffect(() => {
    const run = runtime.current
    if (!run?.initialized || paused || !dirty || !hash || hash === savedHash || phase === 'error') return
    const timer = window.setTimeout(() => { void saveNow() }, 900)
    return () => window.clearTimeout(timer)
  }, [key, dirty, paused, hash, savedHash, phase, saveNow])

  useEffect(() => {
    const saveOnReturn = () => { if (document.visibilityState === 'visible') void saveNow() }
    const saveWhenOnline = () => { void saveNow() }
    document.addEventListener('visibilitychange', saveOnReturn)
    window.addEventListener('online', saveWhenOnline)
    return () => {
      document.removeEventListener('visibilitychange', saveOnReturn)
      window.removeEventListener('online', saveWhenOnline)
    }
  }, [saveNow])

  async function clear() {
    const run = runtime.current
    const current = latest.current
    if (!run || !current.scope) return
    run.clearing = true
    try {
      if (run.operation) await run.operation
      if (run.version > 0) {
        await deleteRecovery(current.scope.workspaceId, run.id, run.version, current.csrf)
      }
      const old = run.id
      run.id = crypto.randomUUID()
      run.version = 0
      run.confirmedHash = ''
      rememberId(key, run.id)
      try { sessionStorage.setItem(`${key}.fresh`, 'true') } catch { /* Explicit discard still works. */ }
      setSavedHash('')
      setSavedAt(null)
      setRecoveredAt(null)
      setCopies((rows) => rows.filter((item) => item.id !== old))
      setPhase('idle')
    } finally { run.clearing = false }
  }

  async function restore(id: string) {
    const run = runtime.current
    const current = latest.current
    if (!run || !current.scope || run.operation || run.clearing) return
    setPhase('loading')
    setError(null)
    try {
      // Finish the current backup before replacing the editor from another copy.
      await saveNow()
      if (current.dirty && current.payload && run.confirmedHash !== JSON.stringify(current.payload)) {
        setPhase('error')
        setError('Back up your current edits before recovering another copy.')
        return
      }
      const view = await getRecovery(current.scope.workspaceId, id)
      run.id = crypto.randomUUID()
      run.version = 0
      run.confirmedHash = ''
      rememberId(key, run.id)
      setSavedHash('')
      current.onRestore(view)
      setRecoveredAt(view.updated_at)
      setPhase('idle')
    } catch (cause) {
      setPhase('error')
      setError(cause instanceof Error ? cause.message : 'This working copy could not be recovered.')
    }
  }

  function retry() {
    if (!runtime.current?.initialized) setAttempt((value) => value + 1)
    else { setPhase('idle'); void saveNow() }
  }

  async function discardCopy(id: string) {
    const current = latest.current
    const copy = copies.find((item) => item.id === id)
    if (!current.scope || !copy || id === runtime.current?.id) return
    try {
      await deleteRecovery(current.scope.workspaceId, id, copy.version, current.csrf)
      setCopies((rows) => rows.filter((item) => item.id !== id))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'This working copy could not be discarded.')
    }
  }

  async function flush() {
    await saveNow()
    // A write already in flight may contain older keystrokes. Save the latest
    // input afterward instead of treating that older acknowledgment as current.
    const run = runtime.current
    const current = latest.current
    if (run && current.payload && current.dirty && run.confirmedHash !== JSON.stringify(current.payload)) {
      await saveNow()
    }
    return !latest.current.dirty || Boolean(run && latest.current.payload &&
      run.confirmedHash === JSON.stringify(latest.current.payload))
  }

  return { phase, error, savedAt, recoveredAt,
    copies: copies.filter((item) => item.id !== runtime.current?.id),
    retry, clear, restore, saveNow, flush, discardCopy,
    loading: Boolean(key) && phase === 'loading',
    protected: dirty && Boolean(hash) && hash === savedHash,
  }
}

export type ProtectedDraftController = ReturnType<typeof useProtectedDraft>
