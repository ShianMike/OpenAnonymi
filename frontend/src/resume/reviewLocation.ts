import { findingCategories } from '../rules/categoryPresentation'
import type { FindingCategory } from '../api/client'

export type ReviewLocation = {
  revision: string
  panel: 'original' | 'preview' | 'findings'
  category: FindingCategory | 'all'
  decision: 'all' | 'pending' | 'decided'
  finding: string | null
  editing: boolean
  plainPreview: boolean
  filtersOpen: boolean
  settingsOpen: boolean
  scroll: { page: number; original: number; preview: number; findings: number; editor: number }
}

const categories: string[] = ['all', ...findingCategories]
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const offset = (value: unknown) => typeof value === 'number' && Number.isFinite(value)
  ? Math.max(0, Math.min(10_000_000, value)) : 0

export function parseReviewLocation(value: unknown): ReviewLocation | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  if (typeof record.revision !== 'string' || !uuid.test(record.revision)) return null
  const scroll = record.scroll && typeof record.scroll === 'object'
    ? record.scroll as Record<string, unknown> : {}
  return {
    revision: record.revision,
    panel: record.panel === 'preview' || record.panel === 'findings' ? record.panel : 'original',
    category: typeof record.category === 'string' && categories.includes(record.category)
      ? record.category as ReviewLocation['category'] : 'all',
    decision: record.decision === 'pending' || record.decision === 'decided' ? record.decision : 'all',
    finding: typeof record.finding === 'string' && uuid.test(record.finding) ? record.finding : null,
    editing: record.editing === true, plainPreview: record.plainPreview === true,
    filtersOpen: record.filtersOpen === true, settingsOpen: record.settingsOpen === true,
    scroll: { page: offset(scroll.page), original: offset(scroll.original),
      preview: offset(scroll.preview), findings: offset(scroll.findings), editor: offset(scroll.editor) },
  }
}

export function readReviewLocation(key: string) {
  try { return parseReviewLocation(JSON.parse(sessionStorage.getItem(key) ?? 'null')) }
  catch { return null }
}

export function writeReviewLocation(key: string, value: ReviewLocation) {
  try { sessionStorage.setItem(key, JSON.stringify(value)) } catch { /* Navigation still works. */ }
}
