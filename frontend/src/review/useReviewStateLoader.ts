import { useEffect, useRef } from 'react'
import { ApiRequestError, getWorkspaceDocuments } from '../api/client'
import { getReviewState } from '../api/reviewState'
import type { ReviewStateView } from '../api/reviewCache'
import { forgetReview } from '../resume/lastReview'
import { messageFrom, sameVersion, type DraftState } from './reviewState'

export type { ReviewStateView } from '../api/reviewCache'

/** One authorized snapshot; protected content stays in the mounted review's memory. */
export function useReviewStateLoader({ documentId, attempt, workspaceIds, userId, scope, onLoaded, onError }: {
  documentId: string | undefined
  attempt: number
  workspaceIds: string
  userId: string
  scope: string
  onLoaded: (snapshot: ReviewStateView) => void
  onError: (state: Extract<DraftState, { kind: 'error' }>) => void
}) {
  const latest = useRef({ onLoaded, onError })
  useEffect(() => { latest.current = { onLoaded, onError } })
  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    getReviewState(documentId, scope, controller.signal)
      .then((snapshot) => {
        if (controller.signal.aborted) return
        const expected = snapshot.source.version
        if (![snapshot.scan, snapshot.findings, snapshot.preview, snapshot.handoff, snapshot.summary]
          .every((view) => view === null || sameVersion(expected, view.version))) {
          latest.current.onError({ kind: 'error', message: 'The review changed while loading. Retry to get one current version.' })
          return
        }
        latest.current.onLoaded(snapshot)
      })
      .catch(async (cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof ApiRequestError && [404, 410].includes(cause.status)) {
          for (const workspace of workspaceIds.split(',').filter(Boolean)) forgetReview(userId, workspace, documentId)
        }
        if (cause instanceof ApiRequestError && cause.status === 410) {
          const lists = await Promise.allSettled(workspaceIds.split(',').filter(Boolean)
            .map((workspace) => getWorkspaceDocuments(workspace, controller.signal)))
          if (controller.signal.aborted) return
          if (lists.some((result) => result.status === 'fulfilled' && result.value
            .some((item) => item.id === documentId && item.status === 'expired'))) {
            latest.current.onError({ kind: 'error', message: 'This document has expired. Its content can no longer be opened.', retryable: false })
            return
          }
        }
        latest.current.onError({ kind: 'error', message: messageFrom(cause),
          retryable: !(cause instanceof ApiRequestError && [404, 410].includes(cause.status)) })
      })
    return () => controller.abort()
  }, [documentId, attempt, workspaceIds, userId, scope])
}
