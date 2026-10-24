import type { DocumentSearchView, SessionView } from '../api/client'
import { pages } from '../shell/navigation'

export type SearchView = 'all' | 'reviews' | 'pages'

const descriptions: Record<string, string> = {
  '/': 'Workspace summary', '/new': 'Start with text or a file', '/documents': 'Browse your reviews',
  '/notifications': 'Your inbox for assignments, comments and approvals', '/rules': 'Detection rules and presets',
  '/activity': 'Workspace event history', '/members': 'People and review assignments',
  '/settings': 'Account, security and workspace settings', '/preferences': 'Light and dark themes, spacing, text size and motion',
}
const quickPages = ['/new', '/documents', '/settings']

export function searchPages(query: string, view: SearchView, administrator: boolean) {
  if (view === 'reviews') return []
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return pages.map(page => ({ ...page, name: page.path === '/preferences' ? 'Appearance & preferences' : page.name,
    description: descriptions[page.path] }))
    .filter(page => (page.path !== '/members' || administrator) && terms.every(term =>
      `${page.name} ${page.description}`.toLocaleLowerCase().includes(term)))
    .filter(page => terms.length > 0 || view === 'pages' || quickPages.includes(page.path))
}

export function mergeSearchResults(previous: DocumentSearchView | null, next: DocumentSearchView): DocumentSearchView {
  const seen = new Set(previous?.items.map(item => item.id))
  const items = [...(previous?.items ?? [])]
  for (const item of next.items) {
    if (seen.has(item.id)) continue
    seen.add(item.id); items.push(item)
  }
  return { ...next, items }
}

export function searchWorkspace(session: SessionView, selected: string, route: string | null, preferred: string | null) {
  return [selected, route, preferred].map(id => session.memberships.find(item => item.workspace_id === id))
    .find(Boolean) ?? session.memberships[0]
}

export function titleParts(title: string, query: string) {
  const term = query.trim()
  if (!term) return [title]
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return title.split(new RegExp(`(${escaped})`, 'ig'))
}
