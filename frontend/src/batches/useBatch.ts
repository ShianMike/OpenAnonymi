import { useCallback, useEffect, useState } from 'react'
import { ApiRequestError } from '../api/client'
import { getBatch, getEligibility, type BatchEligibility, type BatchView } from './api'

const isPageVisible = () => document.visibilityState !== 'hidden'

export function useBatch(id: string) {
  const [data, setData] = useState<{ batch: BatchView; eligibility: BatchEligibility } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const refresh = useCallback(() => setAttempt((value) => value + 1), [])
  useEffect(() => {
    let disposed = false
    let processing = false
    let timer: number | undefined
    let controller: AbortController | undefined
    async function load() {
      if (disposed || !isPageVisible()) return
      controller?.abort()
      controller = new AbortController()
      const current = controller
      try {
        const [batch, eligibility] = await Promise.all([
          getBatch(id, current.signal), getEligibility(id, current.signal),
        ])
        if (disposed || current.signal.aborted) return
        processing = batch.processing
        setData({ batch, eligibility })
        setError(null)
      } catch (cause: unknown) {
        if (disposed || current.signal.aborted) return
        setError(cause instanceof Error ? cause.message : 'The batch could not be loaded.')
        if (cause instanceof ApiRequestError) {
          if ([401, 403, 404, 410].includes(cause.status) || cause.code === 'batch_changed') setData(null)
          // A scan or upload can change the snapshot during authorization.
          // Clear that snapshot and obtain a current one on the ordinary scan interval.
          if (cause.code === 'batch_changed') processing = true
        }
      } finally {
        if (!disposed && !current.signal.aborted && isPageVisible()) {
          timer = window.setTimeout(load, processing ? 5_000 : 60_000)
        }
      }
    }
    function visible() {
      window.clearTimeout(timer)
      controller?.abort()
      if (isPageVisible()) void load()
    }
    void load()
    document.addEventListener('visibilitychange', visible)
    return () => {
      disposed = true
      window.clearTimeout(timer)
      controller?.abort()
      document.removeEventListener('visibilitychange', visible)
    }
  }, [id, attempt])
  return { data: data?.batch.id === id ? data : null, error, refresh }
}
