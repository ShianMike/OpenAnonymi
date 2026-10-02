import { useEffect, useRef, useState } from 'react'
import {
  getDraft,
  getScan,
  getFindings,
  getPreview,
  type SourceView,
  type ScanView,
  type FindingsView,
  type PreviewView,
} from '../api/client'
import { messageFrom, sameVersion, type DraftState } from './reviewState'

export type ReviewSnapshot = {
  saved: SourceView
  scan: ScanView
  findings: FindingsView
  preview: PreviewView
}

/** Refresh the saved baseline without replacing text in the local editor. */
export function useSourceRecovery({
  documentId,
  state,
  enabled,
  applyLatest,
}: {
  documentId: string | undefined
  state: DraftState
  enabled: boolean
  applyLatest: (snapshot: ReviewSnapshot) => void
}) {
  const [pending, setPending] = useState(false)
  const [comparison, setComparison] = useState<ReviewSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scope, setScope] = useState(documentId)
  const requestRef = useRef<AbortController | null>(null)

  if (scope !== documentId) {
    setScope(documentId)
    setComparison(null)
    setError(null)
    setPending(false)
  }
  useEffect(() => {
    return () => {
      requestRef.current?.abort()
      requestRef.current = null
    }
  }, [documentId])

  function cancel() {
    requestRef.current?.abort()
    requestRef.current = null
    setPending(false)
    setComparison(null)
    setError(null)
  }

  async function refresh() {
    if (!documentId || state.kind !== 'ready' || !enabled || requestRef.current) return
    const request = new AbortController()
    requestRef.current = request
    setPending(true)
    setError(null)
    setComparison(null)
    try {
      const [saved, scan, findings, preview] = await Promise.all([
        getDraft(documentId, request.signal),
        getScan(documentId, request.signal),
        getFindings(documentId, request.signal),
        getPreview(documentId, request.signal),
      ])
      if (request.signal.aborted) return
      if (
        !sameVersion(saved.version, scan.version) ||
        !sameVersion(saved.version, findings.version) ||
        !sameVersion(saved.version, preview.version)
      ) {
        throw new Error(
          'The review changed again while loading. Try loading the latest version once more.',
        )
      }
      const latest = { saved, scan, findings, preview }
      if (saved.text !== state.saved.text) setComparison(latest)
      else applyLatest(latest)
    } catch (cause) {
      if (!request.signal.aborted) setError(messageFrom(cause))
    } finally {
      if (requestRef.current === request && !request.signal.aborted) {
        requestRef.current = null
        setPending(false)
      }
    }
  }

  function keepEdits() {
    if (!comparison || pending || !enabled) return
    applyLatest(comparison)
    setComparison(null)
    setError(null)
  }

  return { pending, comparison, error, refresh, keepEdits, cancel }
}
