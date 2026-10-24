import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { MemberView, SessionView } from '../api/client'
import { MembersPage } from './MembersPage'
import { MembersPanel } from './settings/MembersPanel'
import { MemberActionReview } from './settings/MemberDialog'
import { MemberRoleOptions } from './settings/MemberRoleOptions'
import { filteredMembers, memberInitials, memberStatus } from './settings/memberPresentation'

const noop = () => {}
const member = (user_id: string, email: string, role: MemberView['role'] = 'member', extra: Partial<MemberView> = {}): MemberView => ({
  user_id, email, role, revoked_at: null, disabled_at: null, ...extra,
})
const members = [member('z', 'zara@example.invalid'), member('admin', 'alex@example.invalid', 'administrator'),
  member('self', 'nora@example.invalid', 'administrator'), member('revoked', 'remy@example.invalid', 'member', { revoked_at: '2026-10-08T10:00:00Z' }),
  member('disabled', 'devon@example.invalid', 'administrator', { disabled_at: '2026-10-08T10:00:00Z', revoked_at: '2026-10-07T10:00:00Z' })]
const session = { user_id: 'self', csrf_token: 'synthetic', memberships: [{ workspace_id: 'workspace', workspace_name: 'Local test', role: 'administrator' }] } as SessionView

it('uses disabled and revoked access states without treating an invitation as proof of account setup', () => {
  expect(members.map(memberStatus)).toEqual(['active', 'active', 'active', 'revoked', 'disabled'])
  expect(filteredMembers(members, 'self', 'active', '', 'all').map(item => item.user_id)).toEqual(['self', 'admin', 'z'])
  expect(filteredMembers(members, 'self', 'inactive', '', 'all').map(item => item.user_id)).toEqual(['disabled', 'revoked'])
  expect(members.map(item => item.user_id)).toEqual(['z', 'admin', 'self', 'revoked', 'disabled'])
})

it('combines email search, role and access filters and keeps a stable order', () => {
  expect(filteredMembers(members, 'self', 'active', ' ALEX@EXAMPLE ', 'administrator')).toEqual([members[1]])
  expect(filteredMembers(members, 'self', 'active', '', 'member')).toEqual([members[0]])
  expect(filteredMembers(members, 'self', 'inactive', 'remy', 'administrator')).toEqual([])
  expect(filteredMembers(members, 'self', 'active', 'remy', 'all')).toEqual([])
  expect(memberInitials('nora.jones+work@example.invalid')).toBe('NJ')
  expect(memberInitials('local-admin@example.invalid')).toBe('LA')
})

it('shows a person directory with one inspect action per member and separates inactive accounts', () => {
  const render = (view: 'active' | 'inactive') => renderToStaticMarkup(<MembersPanel members={members} session={session} workspaceId="workspace" workspaceName="Local test" view={view} onViewChange={noop} onChanged={noop} onRequestFailed={noop} />)
  const active = render('active')
  expect(active).toContain('aria-label="View nora@example.invalid (you)"')
  expect(active).toContain('Access enabled')
  expect(active).not.toContain('remy@example.invalid')
  expect(active).not.toContain('devon@example.invalid')
  expect(active).not.toContain('<table')
  expect(active).not.toContain('Manage membership')
  const inactive = render('inactive')
  expect(inactive).toContain('Access revoked')
  expect(inactive).toContain('Account disabled')
  expect(inactive).not.toContain('nora@example.invalid')
  expect(inactive).not.toContain('Pending invite')
})

it('explains the actual effects of revocation, restored roles and authenticator recovery', () => {
  const render = (action: 'revoke' | 'restore' | 'reset', target = members[1]) => renderToStaticMarkup(<MemberActionReview action={action} member={target} workspaceName="Local test" />)
  expect(render('revoke')).toContain('All active sessions are ended')
  expect(render('revoke')).toContain('review assignments in this workspace are revoked')
  expect(render('restore')).toContain('Administrator access to Local test is restored')
  expect(render('restore')).toContain('Previous reviewer assignments are not restored automatically')
  expect(render('restore', members[4])).toContain('Restoring workspace membership cannot enable sign-in')
  expect(render('reset')).toContain('sessions and backup codes are invalidated')
  expect(render('reset')).toContain('must administer every workspace')
  expect(render('reset')).not.toContain('role="alertdialog"')
})

it('keeps role inputs in one labelled native group and explains their actual permissions', () => {
  const html = renderToStaticMarkup(<MemberRoleOptions value="member" onChange={noop} />)
  expect(html.match(/type="radio"/g)).toHaveLength(2)
  expect(new Set([...html.matchAll(/name="([^"]+)"/g)].map(match => match[1])).size).toBe(1)
  expect(html.match(/<input[^>]*aria-label="Member"[^>]*>/)?.[0]).toContain('checked=""')
  expect(html).toContain('retention and security policies')
})

it('does not switch to a different administered workspace when the requested workspace is not manageable', () => {
  const value = { ...session, memberships: [...session.memberships, { workspace_id: 'member-workspace', workspace_name: 'Member only', role: 'member' }] } as SessionView
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={['/members?workspace=member-workspace']}><MembersPage session={value} /></MemoryRouter>)
  expect(html).toContain('Only workspace administrators')
  expect(html).not.toContain('Invite member')
  expect(html).not.toContain('Search members')
})
