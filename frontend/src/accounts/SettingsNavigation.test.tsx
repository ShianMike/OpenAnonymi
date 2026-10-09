import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView, WorkspaceSettingsView } from '../api/client'
import { SettingsPage } from './SettingsPage'
import { MembersPage } from './MembersPage'
import { RefreshButton } from '../ui/WorkspaceControls'
import { RetentionPanel } from './settings/RetentionPanel'

const session = { user_id: 'synthetic', email: 'test@example.test', csrf_token: 'synthetic', email_verified: false,
  email_verification_available: false, second_factor_enabled: false, second_factor_setup_required: false,
  memberships: [{ workspace_id: 'synthetic-workspace', workspace_name: 'Test workspace', role: 'administrator', require_second_factor: false }],
} as SessionView
const noop = () => {}
const settings = (route: string, current = session) => renderToStaticMarkup(<MemoryRouter initialEntries={[route]}>
  <SettingsPage session={current} onPasswordChanged={noop} onSignedOut={noop} onSessionChanged={noop} />
</MemoryRouter>)

it('separates personal account from sign-in controls and keeps member management out of Settings', () => {
  const account = settings('/settings')
  expect(account).toContain('test@example.test')
  expect(account).toContain('Manage security')
  expect(account).toContain('Workspace access')
  expect(account).toContain('Administrator')
  expect(account).toContain('href="/?workspace=synthetic-workspace"')
  expect(account).toContain('href="/preferences"')
  expect(account).not.toContain('current-password')
  expect(account).not.toContain('value="members"')
  expect(account).not.toContain('Invite member')
  expect(account).not.toContain('admin-workspace')
  const security = settings('/settings?section=security')
  expect(security).toContain('current-password')
  expect(security).toContain('minLength="12"')
  expect(security).toContain('signs you out on every')
  const member = { ...session, memberships: session.memberships.map(item => ({ ...item, role: 'member' as const })) }
  const memberSettings = settings('/settings?section=retention', member)
  expect(memberSettings).not.toContain('value="retention"')
  const management = renderToStaticMarkup(<MemoryRouter><MembersPage session={member} /></MemoryRouter>)
  expect(management).toContain('Only workspace administrators')
  expect(management).not.toContain('Invite member')
})

it('associates the header save button with the retention form and preserves native limits', () => {
  const workspace: WorkspaceSettingsView = { id: 'synthetic-workspace', name: 'Test workspace', content_retention_days: 7,
    activity_retention_days: 90, settings_version: 1, require_second_factor: false, members_without_second_factor: 0,
    approval_policy: 'owner_choice', active_member_count: 1 }
  const html = renderToStaticMarkup(<RetentionPanel settings={workspace} csrfToken="synthetic" onSaved={noop} onReload={noop} />)
  const formId = html.match(/<form id="([^"]+)"/)?.[1]
  expect(formId).toBeTruthy()
  expect(html).toContain(`type="submit" form="${formId}" disabled=""`)
  expect(html).toContain('min="1" max="30" required=""')
  expect(html).toContain('min="1" max="365" required=""')
})

it('uses one accessible refresh control and blocks duplicate requests while pending', () => {
  const idle = renderToStaticMarkup(<RefreshButton label="Refresh sample" onClick={noop} />)
  expect(idle).toContain('class="refresh-button"')
  expect(idle).toContain('aria-label="Refresh sample"')
  expect(idle).not.toContain('disabled')
  const busy = renderToStaticMarkup(<RefreshButton label="Refresh sample" pending onClick={noop} />)
  expect(busy).toContain('disabled')
  expect(busy).toContain('aria-busy="true"')
  expect(busy).toContain('Refreshing…')
})
