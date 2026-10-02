import { useEffect, useLayoutEffect, useRef } from 'react'
import { rememberReview } from './lastReview'
import { readReviewLocation, writeReviewLocation, type ReviewLocation } from './reviewLocation'

const positions = () => ({
  page: window.scrollY,
  original: document.querySelector('#review-original-panel .document-text')?.scrollTop ?? 0,
  preview: document.querySelector('#review-preview-panel .document-text')?.scrollTop ?? 0,
  findings: document.getElementById('review-findings-panel')?.scrollTop ?? 0,
  editor: document.getElementById('saved-source')?.scrollTop ?? 0,
})

export function useReviewResume({ userId, workspaceId, documentId, ready, revision, location,
  findingIds, dirty, apply }: {
  userId: string; workspaceId: string | null; documentId: string | undefined
  ready: boolean; revision: string | null; location: Omit<ReviewLocation, 'revision' | 'scroll' | 'filtersOpen' | 'settingsOpen'>
  findingIds: string[]; dirty: boolean; apply: (saved: ReviewLocation) => void
}) {
  const key = documentId ? `openanonymi.review-location.${userId}.${documentId}` : ''
  const current = useRef({ location, revision, findingIds, dirty, apply })
  current.current = { location, revision, findingIds, dirty, apply }
  const hydrated = useRef('')
  const scroll = useRef<ReviewLocation['scroll']>(positions())

  function persist() {
    if (!key || hydrated.current !== key || !current.current.revision) return
    writeReviewLocation(key, {
      ...current.current.location, revision: current.current.revision, scroll: scroll.current,
      filtersOpen: (document.getElementById('review-finding-filters') as HTMLDetailsElement | null)?.open ?? false,
      settingsOpen: (document.getElementById('review-suggestion-settings') as HTMLDetailsElement | null)?.open ?? false,
    })
  }

  useLayoutEffect(() => {
    if (!ready || !revision || !key || !workspaceId || !documentId) return
    rememberReview(userId, workspaceId, documentId)
    const saved = readReviewLocation(key)
    hydrated.current = ''
    if (saved) {
      const sameSource = saved.revision === revision
      current.current.apply({ ...saved,
        finding: sameSource && saved.finding && current.current.findingIds.includes(saved.finding) ? saved.finding : null,
        editing: current.current.dirty || saved.editing,
        scroll: sameSource ? saved.scroll : { page: 0, original: 0, preview: 0, findings: 0, editor: 0 },
      })
    }
    let cancelled = false
    let frame = 0
    void document.fonts.ready.then(() => {
      frame = requestAnimationFrame(() => {
        if (cancelled) return
        const offset = saved?.revision === revision ? saved.scroll : { page: 0, original: 0, preview: 0, findings: 0, editor: 0 }
        const filters = document.getElementById('review-finding-filters') as HTMLDetailsElement | null
        const settings = document.getElementById('review-suggestion-settings') as HTMLDetailsElement | null
        if (filters && saved) filters.open = saved.filtersOpen
        if (settings && saved) settings.open = saved.settingsOpen
        for (const [selector, value] of [
          ['#review-original-panel .document-text', offset.original],
          ['#review-preview-panel .document-text', offset.preview],
          ['#review-findings-panel', offset.findings], ['#saved-source', offset.editor],
        ] as const) { const element = document.querySelector(selector); if (element) element.scrollTop = value }
        window.scrollTo({ top: offset.page, behavior: 'instant' })
        scroll.current = positions()
        hydrated.current = key
        persist()
      })
    })
    return () => { cancelled = true; cancelAnimationFrame(frame); hydrated.current = '' }
  // Restore only when this document first becomes ready. Later finding/decision
  // changes preserve the active view rather than replaying an old location.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready, workspaceId])

  useEffect(() => {
    if (hydrated.current === key) persist()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, location.panel, location.category, location.decision, location.finding,
    location.editing, location.plainPreview, revision])

  useLayoutEffect(() => {
    const record = () => { if (hydrated.current === key) { scroll.current = positions(); persist() } }
    window.addEventListener('scroll', record, true)
    document.addEventListener('toggle', record, true)
    const hide = () => { if (document.visibilityState === 'hidden') record() }
    document.addEventListener('visibilitychange', hide)
    return () => {
      record()
      window.removeEventListener('scroll', record, true)
      document.removeEventListener('toggle', record, true)
      document.removeEventListener('visibilitychange', hide)
      hydrated.current = ''
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
}
