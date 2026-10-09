import { API_CREDENTIALS, apiUrl } from './base'
import { ApiRequestError, requireSuccess } from './client'
import { trackedRequest } from './requestActivity'
import { reviewCache, type ReviewStateView } from './reviewCache'
import { getSessionScope } from './sessionEvents'

export async function getReviewState(documentId: string, scope: string, signal: AbortSignal): Promise<ReviewStateView> {
  const epoch = reviewCache.epoch
  const key = `${scope}:${documentId}`
  const cached = scope && scope === getSessionScope() ? reviewCache.get(key) : undefined
  const current = () => !signal.aborted && scope === getSessionScope() && epoch === reviewCache.epoch
  const assertCurrent = () => {
    if (!current()) throw new DOMException('Review request superseded.', 'AbortError')
  }
  return trackedRequest(apiUrl(`/documents/${encodeURIComponent(documentId)}/review-state`), {
    method: 'GET', credentials: API_CREDENTIALS, cache: 'no-store', signal,
    headers: { Accept: 'application/json', ...(cached ? { 'If-None-Match': cached.tag } : {}) },
  }, async response => {
    if (response.status === 304) {
      assertCurrent()
      if (!cached || cached.until <= Date.now() || Date.parse(cached.value.source.expires_at) <= Date.now() || response.headers.get('ETag') !== cached.tag)
        throw new ApiRequestError(409, 'invalid_review_state', 'The review cache changed. Retry.')
      return structuredClone(cached.value)
    }
    try { await requireSuccess(response) }
    catch (cause) { if (scope === getSessionScope()) reviewCache.clear(); throw cause }
    const value = await response.json() as ReviewStateView
    assertCurrent()
    if (value.source.version.document_id !== documentId)
      throw new ApiRequestError(409, 'invalid_review_state', 'The review changed while loading. Retry.')
    reviewCache.put(key, value, response.headers.get('ETag') ?? '')
    return value
  })
}
