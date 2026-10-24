import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom'
import { ApiRequestError, type SessionView, type WorkspaceSettingsView } from '../api/client'
import { SettingsPage } from './SettingsPage'
import { MembersPage } from './MembersPage'
import { RefreshButton } from '../ui/WorkspaceControls'
import { RetentionPanel } from './settings/RetentionPanel'
import { WorkspaceSecurityPanel } from './settings/WorkspaceSecurityPanel'
import { settingsHref, settingsSections, validRetention, workspaceSettingsError } from './settings/settingsNavigation'
import type { ReactNode } from 'react'

const session = { user_id: 'synthetic', email: 'test@example.test', csrf_token: 'synthetic', email_verified: false,
  email_verification_available: false, second_factor_enabled: false, second_factor_setup_required: false,
  memberships: [{ workspace_id: 'synthetic-workspace', workspace_name: 'Test workspace', role: 'administrator', require_second_factor: false }],
} as SessionView
const noop = () => {}
function render(element: ReactNode, route = '/settings') {
  const router = createMemoryRouter([{ path: '*', element }], { initialEntries: [route] })
  return renderToStaticMarkup(<RouterProvider router={router} />)
}
const settings = (route: string, current = session) => render(<SettingsPage session={current} onPasswordChanged={noop} onSignedOut={noop} onSessionChanged={noop} />, route)
const workspace: WorkspaceSettingsView = { id: 'synthetic-workspace', name: 'Test workspace', content_retention_days: 7,
  activity_retention_days: 90, settings_version: 1, require_second_factor: false, members_without_second_factor: 1,
  approval_policy: 'owner_choice', active_member_count: 1 }

it('uses distinct personal and workspace destinations with appearance inside settings', () => {
  const account = settings('/settings')
  expect(account).toContain('test@example.test')
  expect(account).toContain('Workspace memberships')
  expect(account).toContain('Administrator')
  expect(account).toContain('href="/?workspace=synthetic-workspace"')
  expect(account).toContain('href="/settings?section=appearance"')
  expect(account).toContain('Appearance &amp; preferences')
  expect(account).toContain('aria-label="Settings sections"')
  expect(account).not.toContain('role="tablist"')
  expect(account).not.toContain('current-password')
  expect(account).not.toContain('Invite member')
  expect(account).not.toContain('Send me email updates')
})

it('keeps passwords and authenticator controls separate from device sessions and workspace policies', () => {
  const security = settings('/settings?section=security')
  expect(security).toContain('current-password')
  expect(security).toContain('minLength="12"')
  expect(security).toContain('signs you out on every')
  expect(security).not.toContain('Require reviewer approval for every export')
  expect(security).not.toContain('Sign out all other sessions')
  const devices = settings('/settings?section=devices')
  expect(devices).toContain('Sign out all other sessions')
  expect(devices).toContain('A browser can appear more than once')
  expect(devices).not.toContain('current-password')
  expect(settings('/settings?section=notifications')).toContain('Open your notification inbox')
})

it('does not substitute another administered workspace for an explicitly unauthorized scope', () => {
  const member = { ...session, memberships: session.memberships.map(item => ({ ...item, role: 'member' as const })) }
  const denied = settings('/settings?section=retention', member)
  expect(denied).toContain('Only workspace administrators')
  expect(denied).toContain('Administrator access needed')
  expect(denied).toContain('Back to account')
  expect(denied).not.toContain('value="retention"')
  const mixed = { ...session, memberships: [...session.memberships, { ...member.memberships[0], workspace_id: 'member-only' }] }
  const wrongScope = settings('/settings?section=workspace&workspace=member-only', mixed)
  expect(wrongScope).toContain('Only workspace administrators')
  expect(wrongScope).toContain('No administrator access')
  expect(wrongScope).not.toContain('settings-policies-form')
  const management = renderToStaticMarkup(<MemoryRouter><MembersPage session={member} /></MemoryRouter>)
  expect(management).toContain('Only workspace administrators')
})

it('distinguishes lost access, session problems and connection failures when recovering settings', () => {
  const denied = workspaceSettingsError(new ApiRequestError(404, 'workspace_not_found', 'Workspace not found.'))
  expect(denied.title).toBe('Workspace access unavailable')
  expect(denied.message).toContain('Administrator access is required')
  expect(denied.retryLabel).toBe('Check access again')
  const sessionEnded = workspaceSettingsError(new ApiRequestError(401, 'session_expired', 'Sign in again.'))
  expect(sessionEnded.title).toBe('Your session needs to be refreshed')
  expect(sessionEnded.retryLabel).toBe('Check session again')
  const network = workspaceSettingsError(new TypeError('Failed to fetch'))
  expect(network.message).toContain('Check your connection')
  expect(network.message).not.toContain('Failed to fetch')
  expect(network.retryLabel).toBe('Try again')
  expect(workspaceSettingsError(new ApiRequestError(503, 'unavailable', 'The service is temporarily unavailable.')).message).toBe('The service is temporarily unavailable.')
})

it('keeps retention actions inside the form with native bounds and a staged review step', () => {
  const html = render(<RetentionPanel settings={workspace} csrfToken="synthetic" onSaved={noop} onReload={noop} onRequestFailed={noop} />)
  expect(html).toContain('min="1" max="30" step="1" required=""')
  expect(html).toContain('min="1" max="365" step="1" required=""')
  expect(html).toMatch(/type="submit"[^>]*disabled=""[^>]*>Review changes/)
  expect(html).toContain('Existing review expiry dates stay the same')
  expect(html).toContain('Older records become eligible for scheduled cleanup')
  expect(html).not.toContain('retention-cards')
})

it('shows the real workspace policy prerequisites and independent approval limitation', () => {
  const renderPolicies = (value: WorkspaceSettingsView) => render(<WorkspaceSecurityPanel settings={value} session={session} onSaved={noop} onReload={noop} onRequestFailed={noop} />)
  const html = renderPolicies(workspace)
  expect(html).toContain('Enable two-step verification on your account first')
  expect(html).toContain('1 active member has no two-step verification')
  expect(html).toContain('Review changes')
  const enforced = renderPolicies({ ...workspace, approval_policy: 'always' })
  expect(enforced).toContain('This workspace has one active member')
  expect(enforced).toContain('Manage members')
})

it('validates whole-day retention values before opening a save confirmation', () => {
  expect(validRetention('1', '1')).toBe(true)
  expect(validRetention('30', '365')).toBe(true)
  for (const [content, activity] of [['', '90'], ['7', ''], ['0', '90'], ['31', '90'], ['7', '366'], ['7', '0'], ['7.5', '90'], ['7', '1.5'], ['NaN', '90'], ['7', 'Infinity']]) expect(validRetention(content, activity)).toBe(false)
})

it('preserves workspace context in links and uses distinct settings destinations', () => {
  expect(settingsHref('retention', 'space & name')).toBe('/settings?section=retention&workspace=space+%26+name')
  expect(settingsHref('appearance', null)).toBe('/settings?section=appearance')
  expect(new Set(settingsSections.map(item => item.id)).size).toBe(settingsSections.length)
  expect(settingsSections.filter(item => item.group === 'workspace').map(item => item.id)).toEqual(['workspace', 'retention'])
})

it('uses one accessible refresh control and blocks duplicate requests while pending', () => {
  const idle = renderToStaticMarkup(<RefreshButton label="Refresh sample" onClick={noop} />)
  expect(idle).toContain('class="refresh-button"')
  expect(idle).toContain('aria-label="Refresh sample"')
  expect(idle).not.toContain('disabled')
  const busy = renderToStaticMarkup(<RefreshButton label="Refresh sample" pending onClick={noop} />)
  expect(busy).toContain('disabled')
  expect(busy).toContain('aria-busy="true"')
})
