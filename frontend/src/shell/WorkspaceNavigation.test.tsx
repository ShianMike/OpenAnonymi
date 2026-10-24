import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { Sidebar } from './Sidebar'
import { workspaceHref } from './navigation'
import { RulesPage } from '../workspace/RulesPage'

const appearance = vi.hoisted(() => ({ preference: 'light' as 'light' | 'dark' | 'system', setAppearance: () => {} }))
vi.mock('../appearance/useAppearance', () => ({ useAppearance: () => appearance }))

it('keeps workspace links and rules in the selected authorized workspace, with a safe fallback', () => {
  const session = { user_id: 'synthetic', csrf_token: 'synthetic', memberships: [
    { workspace_id: 'first', workspace_name: 'First workspace', role: 'member' },
    { workspace_id: 'second', workspace_name: 'Second workspace', role: 'administrator' },
  ] } as SessionView
  const render = (route: string) => renderToStaticMarkup(<MemoryRouter initialEntries={[route]}>
    <Sidebar session={session} menuOpen={false} onClose={() => {}} navRef={{ current: null }} />
    <RulesPage session={session} />
  </MemoryRouter>)
  const selected = render('/rules?workspace=second')
  expect(selected).toContain('aria-label="Switch workspace"')
  expect(selected).toContain('aria-label="Appearance: Light"')
  expect(selected).toMatch(/id="sidebar-workspace"[\s\S]*?<strong>Second workspace<\/strong>[\s\S]*?<small>Administrator<\/small>[\s\S]*?<\/button>/)
  for (const path of ['/documents', '/new', '/rules', '/activity', '/members', '/settings']) {
    expect(selected).toContain(`href="${path}?workspace=second"`)
  }
  expect(selected).not.toContain('href="/continue')
  expect(selected).not.toContain('Continue review')
  expect(render('/rules?workspace=second&view=presets')).toContain('/new?workspace=second&amp;preset=')
  expect(selected).not.toContain('Select a workspace on each page')
  expect(selected).not.toContain('Your review. Your call.')
  const invalid = render('/rules?workspace=not-a-member')
  expect(invalid).toContain('href="/documents?workspace=first"')
  expect(invalid).not.toContain('href="/documents?workspace=not-a-member"')
  expect(workspaceHref('/notifications', 'second')).toBe('/notifications')
  expect(workspaceHref('/preferences', 'second')).toBe('/preferences')
  expect(workspaceHref('/documents', 'id with spaces')).toBe('/documents?workspace=id%20with%20spaces')
})

it.each(['light', 'dark', 'system'] as const)('shows the saved %s preference in the sidebar appearance menu trigger', (preference) => {
  appearance.preference = preference
  try {
    const html = renderToStaticMarkup(<MemoryRouter><Sidebar
      session={{ user_id: 'synthetic', csrf_token: 'synthetic', memberships: [] } as SessionView}
      menuOpen={false} onClose={() => {}} navRef={{ current: null }}
    /></MemoryRouter>)
    const label = { light: 'Light', dark: 'Dark', system: 'System' }[preference]
    const trigger = html.match(/<button[^>]*aria-label="Appearance: [^"]*"[^>]*>/)?.[0]
    expect(trigger).toContain(`aria-label="Appearance: ${label}"`)
    expect(trigger).toContain('aria-haspopup="menu"')
    expect(html.indexOf('Legal &amp; support')).toBeLessThan(html.indexOf('Powered by OpenAnonymi'))
    expect(html.match(/Powered by OpenAnonymi/g)).toHaveLength(1)
    expect(html).not.toContain('sidebar-theme-options')
  } finally { appearance.preference = 'light' }
})
