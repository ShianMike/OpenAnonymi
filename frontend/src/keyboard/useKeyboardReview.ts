import { useEffect, useRef, useState } from 'react'
import type { VersionRef, StyleChoice } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { reviewShortcut } from './shortcuts'
import { availableChoices } from '../review/useStyleControls'

type KeepTarget = { finding: string; version: VersionRef }

export function useKeyboardReview(review: ReviewController, userId: string) {
  const key = `openanonymi.keyboard-review.${userId}`
  const [enabled, setEnabled] = useState(() => { try { return localStorage.getItem(key) === 'true' } catch { return false } })
  const [savedPreference, setSavedPreference] = useState(true)
  const [help, setHelp] = useState(false)
  const [keep, setKeep] = useState<KeepTarget | null>(null)
  const [generalize, setGeneralize] = useState<KeepTarget | null>(null)
  const [reason, setReason] = useState<'' | 'false_match' | 'intended_disclosure'>('')
  const [pending, setPending] = useState(false)
  const inFlight = useRef(false)
  const keepFocus = useRef<HTMLElement | null>(null)
  const latest = useRef({ review, help, keep, generalize })
  useEffect(() => { latest.current = { review, help, keep, generalize } })
  const blocked = review.actionPending || review.conflict || review.dirty || review.settingsDirty || Boolean(review.groupConfirmation)
  function toggle(value: boolean) {
    setEnabled(value)
    try { localStorage.setItem(key, String(value)); setSavedPreference(true) } catch { setSavedPreference(false) }
  }
  function restoreKeepFocus(event: Event) {
    const target = keepFocus.current
    if (target?.isConnected && target.getClientRects().length > 0) {
      event.preventDefault()
      target.focus({ preventScroll: true })
    }
  }
  async function perform(action: 'label' | 'redact' | 'keep' | 'undo', finding?: string, explicitReason?: 'false_match' | 'intended_disclosure', choice?: StyleChoice) {
    if (inFlight.current) return
    inFlight.current = true; setPending(true)
    try {
      if (action === 'undo') await latest.current.review.undoReview()
      else if (finding) {
        const saved = await latest.current.review.changeReview('decision', finding, { action, groupScope: false, keepReason: explicitReason, choice })
        if (saved) { setKeep(null); setGeneralize(null) }
      }
    } finally { inFlight.current = false; setPending(false) }
  }
  useEffect(() => {
    if (!enabled) return
    function handle(event: KeyboardEvent) {
      const action = reviewShortcut(event)
      if (!action) return
      const target = event.target
      if (target instanceof Element && (target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"]') || (target instanceof HTMLElement && target.isContentEditable))) return
      if (Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], .finding-popover'))
        .some((element) => element.getClientRects().length > 0)) return
      const { review: current, help: helpOpen, keep: keepOpen, generalize: generalizeOpen } = latest.current
      if (helpOpen || keepOpen || generalizeOpen || inFlight.current || current.state.kind !== 'ready') return
      if (action === 'help') { event.preventDefault(); setHelp(true); return }
      if (current.actionPending || current.conflict || current.dirty || current.settingsDirty || current.groupConfirmation) return
      const findings = current.visibleFindings
      const selected = findings.find((item) => item.finding_id === current.selectedFindingId)
      if (action === 'next' || action === 'previous') {
        if (!findings.length) return
        const index = findings.findIndex((item) => item.finding_id === current.selectedFindingId)
        const next = index < 0 ? (action === 'next' ? 0 : findings.length - 1)
          : (index + (action === 'next' ? 1 : -1) + findings.length) % findings.length
        event.preventDefault(); current.locateFinding(findings[next].finding_id, 'source'); return
      }
      if (action === 'undo') { if (!current.undoCount) return; event.preventDefault(); void perform('undo'); return }
      if (!selected) return
      event.preventDefault()
      if (action === 'mask' || action === 'fictional' || action === 'shift' || action === 'generalize') {
        const decisionAction = action === 'mask' || action === 'generalize' ? 'redact' : 'label'
        const style = action === 'mask' ? 'partial_mask' : action === 'fictional' ? 'stand_in' : action === 'shift' ? 'date_shift' : 'generalize'
        const choices = availableChoices(current.preview, selected, decisionAction).filter((choice) => choice.style === style)
        if (!choices.length) {
          current.setNotice(action === 'fictional' ? 'Fictional stand-ins aren’t available for this category or number. Try a partial mask.' : action === 'mask' ? 'Partial masks aren’t available for this finding.' : 'This style needs a parsed date; age bands also need a birth date.'); return
        }
        if (action === 'generalize') { setGeneralize({ finding: selected.finding_id, version: current.state.saved.version }); return }
        const defaults = current.state.saved.category_defaults[selected.category]
        const preferred = choices.find((choice) => defaults?.style === choice.style && defaults?.style_option === choice.style_option) ?? choices[0]
        void perform(decisionAction, selected.finding_id, undefined, preferred); return
      }
      if (action === 'keep') {
        const panel = document.getElementById(current.mobilePanel === 'preview' ? 'review-preview-panel' : 'review-original-panel')
        keepFocus.current = panel?.querySelector<HTMLElement>(`.inline-finding[data-finding-id="${CSS.escape(selected.finding_id)}"]`) ?? null
        setReason(''); setKeep({ finding: selected.finding_id, version: current.state.saved.version })
      }
      else void perform(action, selected.finding_id)
    }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  // Event handling reads the latest committed controller, never a stale review version.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled])
  return { enabled, toggle, savedPreference, help, setHelp, keep, setKeep, generalize, setGeneralize, reason, setReason, pending, blocked, perform, restoreKeepFocus }
}
