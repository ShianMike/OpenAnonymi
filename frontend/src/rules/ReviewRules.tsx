import { useEffect, useState } from 'react'
import type { ReviewController } from '../review/useReviewController'
import { getRuleSnapshot, refreshRules, type RuleSnapshot } from './api'

export function ReviewRules({ review, csrf }: { review: ReviewController; csrf: string }) {
  const [snapshot, setSnapshot] = useState<RuleSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const version = review.state.kind === 'ready' ? review.state.saved.version.settings_version : null
  useEffect(() => {
    if (!review.documentId || !version) return
    const controller = new AbortController()
    getRuleSnapshot(review.documentId, controller.signal).then((value) => { if (!controller.signal.aborted) setSnapshot(value) })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Rules could not be loaded.') })
    return () => controller.abort()
  }, [review.documentId, version, attempt])
  async function apply() {
    if (!review.documentId || review.state.kind !== 'ready') return
    setPending(true); setError(null)
    try { await refreshRules(review.documentId, review.state.saved.version, csrf); setConfirm(false); review.reloadSaved() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Rules could not be updated.') }
    finally { setPending(false) }
  }
  const blocked = pending || review.actionPending || review.dirty || review.settingsDirty || review.conflict
  return <div className="review-workspace-rules"><strong>Workspace detection rules</strong>
    {snapshot && <><p className="field-note">{snapshot.rules.length ? snapshot.rules.map((rule) => `${rule.name} · v${rule.version}`).join(', ') : 'No custom rules saved for this review.'}</p>
      {snapshot.update_available && (!confirm ? <button type="button" disabled={blocked} onClick={() => setConfirm(true)}>Use latest workspace rules</button>
        : <div role="alert"><p>This resets automatic suggestions and review confirmation. Run a new scan and review the findings.</p>
          <button type="button" disabled={blocked} onClick={() => void apply()}>Update rules and review again</button>{' '}
          <button type="button" disabled={pending} onClick={() => setConfirm(false)}>Cancel</button></div>)}</>}
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(null); setAttempt((value) => value + 1) }}>Retry rules</button></p>}
  </div>
}
