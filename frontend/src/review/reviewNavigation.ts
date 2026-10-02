import type { Dispatch, SetStateAction } from 'react'
import type { FindingsView, FindingCategory } from '../api/client'
import type { DraftState } from './reviewState'

type Update<T> = Dispatch<SetStateAction<T>>

export function createReviewNavigation({ state, findings, blocked, selectedFindingId,
  setSelectedFindingId, setMobilePanel, setEditingSource, setPlainPreview,
  setCategoryFilter, setDecisionFilter }: {
  state: DraftState; findings: FindingsView | null; blocked: boolean
  selectedFindingId: string | null; setSelectedFindingId: Update<string | null>
  setMobilePanel: Update<'original' | 'preview' | 'findings'>
  setEditingSource: Update<boolean>; setPlainPreview: Update<boolean>
  setCategoryFilter: Update<FindingCategory | 'all'>
  setDecisionFilter: Update<'all' | 'pending' | 'decided'>
}) {
  function locateFinding(findingId: string, target: 'source' | 'preview') {
    if (state.kind !== 'ready' || !findings || blocked) return
    if (!findings.findings.some((item) => item.finding_id === findingId)) return
    setSelectedFindingId(findingId)
    setMobilePanel(target === 'source' ? 'original' : 'preview')
    setEditingSource(false)
    setPlainPreview(false)
    requestAnimationFrame(() => {
      const card = document.getElementById(`finding-${findingId}`)
      if (card && card.getClientRects().length > 0) card.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      const panel = document.getElementById(target === 'source' ? 'review-original-panel' : 'review-preview-panel')
      const mark = panel?.querySelector<HTMLButtonElement>(`.inline-finding[data-finding-id="${CSS.escape(findingId)}"]`)
      mark?.scrollIntoView({ block: 'center', inline: 'nearest' })
      mark?.focus({ preventScroll: true })
    })
  }

  function nextUnresolved() {
    const pending = findings?.findings.filter((item) => item.action === null) ?? []
    if (!pending.length) return
    const index = pending.findIndex((item) => item.finding_id === selectedFindingId)
    setCategoryFilter('all')
    setDecisionFilter('all')
    locateFinding(pending[(index + 1) % pending.length].finding_id, 'source')
  }
  return { locateFinding, nextUnresolved }
}
