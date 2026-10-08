import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { GlassSelect } from '../../ui/GlassSelect'
import type { ReviewController } from '../useReviewController'
import type { ReviewFinding } from '../textSegments'

export function FindingAdvanced({
  review,
  item,
}: {
  review: ReviewController
  item: ReviewFinding
}) {
  const [open, setOpen] = useState(false)
  const {
    state,
    findings,
    preview,
    selection,
    dirty,
    settingsDirty,
    findingPending,
    scanPending,
    conflict,
    activeFindings,
    groupTriggerRef,
    groupConfirmRef,
    groupConfirmation,
    setGroupConfirmation,
    changeFinding,
    changeReview,
    confirmGroupDecision,
    cancelGroupDecision,
    mergeTargets,
    setMergeTargets,
    showExactMatches,
    locateFinding,
    exactMatches,
  } = review
  if (state.kind !== 'ready' || !findings) return null
  const linkTargets = open ? findings.findings.filter((candidate) =>
    candidate.finding_id !== item.finding_id && candidate.category === item.category &&
    (!item.group_id || candidate.group_id !== item.group_id)) : []
  return (
    <details className="finding-more" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>More finding actions <ChevronDown size={14} aria-hidden="true" /></summary>
      {open && <div className="finding-extra-actions">
        <div className="finding-action-section">
          <h4>Find in the text</h4>
          <div className="finding-locate-actions">
            <button type="button" onClick={() => locateFinding(item.finding_id, 'source')} disabled={dirty || settingsDirty}>Locate original</button>
            {preview?.mappings.some((mapping) => mapping.finding_id === item.finding_id) && (
              <button type="button" onClick={() => locateFinding(item.finding_id, 'preview')} disabled={dirty || settingsDirty || preview.status === 'conflict'}>Locate preview</button>
            )}
          </div>
          <button type="button" onClick={() => void showExactMatches(item.finding_id)} disabled={dirty || settingsDirty || findingPending || conflict}>Find other identical text</button>
          {exactMatches?.findingId === item.finding_id && (
            <div className="finding-exact-matches">
              <p>{exactMatches.result.spans.length} unmarked exact matches{exactMatches.result.truncated ? ' (first 100 shown)' : ''}.</p>
              {exactMatches.result.spans.map((span) => <button key={span.start} type="button"
                onClick={() => void changeReview('exact', item.finding_id, { span })} disabled={findingPending || conflict}>
                Mark characters {span.start + 1}–{span.end}
              </button>)}
            </div>
          )}
        </div>
        <div className="finding-action-section">
          <h4>Adjust the highlight</h4>
          <p>Select the right words in the original text, then update this highlight.</p>
        <button
          type="button"
          onClick={() => void changeFinding('revise', item.finding_id)}
          disabled={
            !selection ||
            activeFindings.some(
              (other) =>
                other.finding_id !== item.finding_id &&
                selection.start < other.span.end &&
                other.span.start < selection.end,
            ) ||
            dirty ||
            settingsDirty ||
            findingPending ||
            scanPending ||
            conflict
          }
        >
          Use selected range
        </button>
        </div>
        {item.group_id &&
          findings.findings.filter((candidate) => candidate.group_id === item.group_id).length >
            1 && (
            <div className="finding-action-section">
              <h4>Linked details</h4>
              <button
                type="button"
                onClick={() => void changeReview('split', item.finding_id)}
                disabled={dirty || settingsDirty || findingPending || conflict}
              >
                Review separately
              </button>{' '}
              {(['label', 'redact', 'keep'] as const).map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={(event) => {
                    const members = findings.findings.filter(
                      (candidate) => candidate.group_id === item.group_id,
                    )
                    groupTriggerRef.current = event.currentTarget
                    setGroupConfirmation({
                      findingId: item.finding_id,
                      action,
                      affectedIds: members.map((member) => member.finding_id),
                      spans: members.map((member) => member.span),
                      version: state.saved.version,
                    })
                  }}
                  disabled={dirty || settingsDirty || findingPending || conflict}
                >
                  {action === 'label' ? 'Label' : action === 'redact' ? 'Redact' : 'Keep'} all
                  linked
                </button>
              ))}
              {groupConfirmation?.findingId === item.finding_id && !groupConfirmation.choice && (
                <div role="group" aria-label="Confirm group decision">
                  <p>
                    Apply {groupConfirmation.action} to {groupConfirmation.affectedIds.length}{' '}
                    occurrences at{' '}
                    {groupConfirmation.spans
                      .map((span) => `${span.start + 1}–${span.end}`)
                      .join(', ')}
                    ?
                  </p>
                  <button
                    ref={groupConfirmRef}
                    type="button"
                    onClick={confirmGroupDecision}
                    disabled={dirty || settingsDirty || findingPending || conflict}
                  >
                    Apply to all linked
                  </button>{' '}
                  <button type="button" onClick={cancelGroupDecision}>
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        {linkTargets.length > 0 && <div className="finding-action-section">
        <label htmlFor={`merge-${item.finding_id}`}>Link with another occurrence</label>
        <GlassSelect
          id={`merge-${item.finding_id}`}
          value={mergeTargets[item.finding_id] || ''}
          disabled={dirty || settingsDirty || findingPending || conflict}
          onValueChange={(value) =>
            setMergeTargets((current) => ({
              ...current,
              [item.finding_id]: value,
            }))
          }
        >
          <option value="">Choose occurrence</option>
          {linkTargets
            .map((candidate) => (
              <option key={candidate.finding_id} value={candidate.finding_id}>
                {review.codePoints.slice(candidate.span.start, Math.min(candidate.span.end, candidate.span.start + 48)).join('')}{candidate.span.end - candidate.span.start > 48 ? '…' : ''} · {candidate.span.start + 1}–{candidate.span.end}
              </option>
            ))}
        </GlassSelect>{' '}
        <button
          type="button"
          onClick={() => void changeReview('merge', item.finding_id)}
          disabled={
            !mergeTargets[item.finding_id] || dirty || settingsDirty || findingPending || conflict
          }
        >
          Link occurrences
        </button>
        </div>}
        <div className="finding-action-section finding-remove-action">
          <button type="button" onClick={() => void changeFinding('remove', item.finding_id)}
            disabled={dirty || settingsDirty || findingPending || scanPending || conflict}>Remove finding</button>
          <p>Removes this highlight. Your original text stays intact.</p>
        </div>
      </div>}
    </details>
  )
}
