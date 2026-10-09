import { useEffect, useRef, useState } from 'react'
import { decideFindings, getPreview, type FindingsView, type PreviewView } from '../api/client'
import { getSessionScope, subscribeSessionEnded } from '../api/sessionEvents'
import { DecisionQueue, type QueuedDecision } from './decisionQueue'

export function useDecisionQueue({ documentId, csrf, generation, onFindings, onPreview, onStart, onFailed }: {
  documentId: string | undefined
  csrf: string
  generation: number
  onFindings: (findings: FindingsView, acknowledged: boolean) => void
  onPreview: (preview: PreviewView) => void
  onStart: () => void
  onFailed: (cause: unknown) => void
}) {
  const [pending, setPending] = useState(false)
  const [pendingIds, setPendingIds] = useState<string[]>([])
  const queue = useRef<DecisionQueue | null>(null)
  const latest = useRef({ onFindings, onPreview, onStart, onFailed })
  useEffect(() => { latest.current = { onFindings, onPreview, onStart, onFailed } })
  useEffect(() => {
    if (!documentId) return
    const current = new DecisionQueue(
      (job, expected, signal) => decideFindings(documentId, job.findingId, expected, job.action,
        job.keepReason, job.groupScope, job.ids, csrf, job.choice, signal),
      (_expected, signal) => getPreview(documentId, signal),
      {
        render: (findings, ids, active, acknowledged) => {
          if (getSessionScope() !== csrf) return
          setPending(active); setPendingIds(ids); latest.current.onFindings(findings, acknowledged)
        },
        preview: value => { if (getSessionScope() === csrf) latest.current.onPreview(value) },
        failed: cause => { if (getSessionScope() === csrf) latest.current.onFailed(cause) },
      },
    )
    queue.current = current
    const remove = subscribeSessionEnded(scope => { if (scope === csrf) current.close() })
    return () => { remove(); current.close(); if (queue.current === current) queue.current = null }
  }, [documentId, csrf, generation])
  return { pending, pendingIds,
    enqueue: (base: FindingsView, job: QueuedDecision) => {
      if (getSessionScope() !== csrf || !queue.current) return false
      const accepted = queue.current.enqueue(base, job)
      if (accepted) latest.current.onStart()
      return accepted
    },
    flush: () => queue.current?.flush() ?? Promise.resolve(false),
    cancel: () => { queue.current?.close(); setPending(false); setPendingIds([]) },
  }
}
