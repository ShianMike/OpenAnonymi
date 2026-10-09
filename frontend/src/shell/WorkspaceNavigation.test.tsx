import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { Sidebar } from './Sidebar'
import { workspaceHref } from './navigation'
import { RulesPage } from '../workspace/RulesPage'

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
  expect(selected).toMatch(/id="sidebar-workspace"[\s\S]*?<strong>Second workspace<\/strong>[\s\S]*?<small>Administrator<\/small>[\s\S]*?<\/button>/)
  for (const path of ['/documents', '/new', '/continue', '/rules', '/activity', '/members', '/settings']) {
    expect(selected).toContain(`href="${path}?workspace=second"`)
  }
  expect(selected).toContain('/new?workspace=second&amp;preset=')
  expect(selected).not.toContain('Select a workspace on each page')
  expect(selected).not.toContain('Your review. Your call.')
  const invalid = render('/rules?workspace=not-a-member')
  expect(invalid).toContain('href="/documents?workspace=first"')
  expect(invalid).not.toContain('href="/documents?workspace=not-a-member"')
  expect(workspaceHref('/notifications', 'second')).toBe('/notifications')
  expect(workspaceHref('/preferences', 'second')).toBe('/preferences')
  expect(workspaceHref('/documents', 'id with spaces')).toBe('/documents?workspace=id%20with%20spaces')
})
