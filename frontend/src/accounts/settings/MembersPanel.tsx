import { useRef, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import * as Popover from '@radix-ui/react-popover'
import { ChevronRight, Search, ShieldCheck, Users, X } from 'lucide-react'
import type { MemberView, SessionView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ListPagination } from '../../ui/ListPagination'
import { pageWindow } from '../../ui/pagination'
import { MemberDialog } from './MemberDialog'
import { memberInitials, memberStatus, memberStatusLabel, memberRoles, filteredMembers } from './memberPresentation'

export function MembersPanel({ members, session, workspaceId, workspaceName, view, onViewChange, onChanged, onRequestFailed }: {
  members: MemberView[]; session: SessionView; workspaceId: string; workspaceName: string
  view: 'active' | 'inactive'; onViewChange: (view: 'active' | 'inactive') => void
  onChanged: (member: MemberView, message: string) => void; onRequestFailed: (cause: unknown) => void
}) {
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('all')
  const [pagination, setPagination] = useState({ view, page: 0 })
  const searchInput = useRef<HTMLInputElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const active = members.filter(member => memberStatus(member) === 'active').length
  const filtered = filteredMembers(members, session.user_id, view, search, role)
  const range = pageWindow(filtered.length, pagination.view === view ? pagination.page : 0, 12)
  const hasFilters = !!search.trim() || role !== 'all'
  function reset() { setSearch(''); setRole('all'); setPagination({ view, page: 0 }); searchInput.current?.focus() }
  return <Tabs.Root className="people-directory" value={view} onValueChange={value => { setPagination({ view, page: 0 }); onViewChange(value as 'active' | 'inactive') }}>
    <div className="people-navigation"><Tabs.List className="people-tabs" aria-label="Member access views">
      <Tabs.Trigger value="active">Active<span>{active}</span></Tabs.Trigger>
      <Tabs.Trigger value="inactive">Inactive<span>{members.length - active}</span></Tabs.Trigger>
    </Tabs.List><Popover.Root><Popover.Trigger className="people-guide-trigger"><ShieldCheck size={14} aria-hidden="true" />Roles & access</Popover.Trigger>
      <Popover.Portal><Popover.Content className="people-role-guide" align="end" sideOffset={8} collisionPadding={12} aria-label="Workspace roles and document access">
        <Popover.Close className="people-guide-close" aria-label="Close roles guide"><X size={16} aria-hidden="true" /></Popover.Close>
        <h2>Roles & access</h2><dl>{Object.entries(memberRoles).map(([key, item]) => <div key={key}><dt>{item.label}</dt><dd>{item.description}</dd></div>)}</dl>
        <p>Both roles can only open documents they own or are assigned to review. Being an administrator does not grant access to everyone’s documents.</p>
        <p>Another administrator must change your own role. The last active administrator is protected from removal.</p>
      </Popover.Content></Popover.Portal>
    </Popover.Root></div>
    <Tabs.Content value={view} className="people-view">
      <h2 ref={heading} tabIndex={-1} className="sr-only">{view === 'active' ? 'People with workspace access' : 'People without workspace access'}</h2>
      <div className="people-toolbar"><div className="people-search"><Search size={15} aria-hidden="true" /><input ref={searchInput} type="search" aria-label="Search members" placeholder="Search by email…" autoComplete="off" value={search} onChange={event => { setSearch(event.target.value); setPagination({ view, page: 0 }) }} />
        {search && <button type="button" aria-label="Clear member search" onClick={() => { setSearch(''); setPagination({ view, page: 0 }); searchInput.current?.focus() }}><X size={14} aria-hidden="true" /></button>}
      </div><GlassSelect id="people-role-filter" aria-label="Filter members by role" value={role} onValueChange={value => { setRole(value); setPagination({ view, page: 0 }) }}><option value="all">All roles</option><option value="administrator">Administrators</option><option value="member">Members</option></GlassSelect>
        {hasFilters && <button type="button" className="people-reset" onClick={reset}>Reset</button>}
      </div>
      {filtered.length ? <ul className="people-list" aria-label={view === 'active' ? 'Active members' : 'Inactive members'}>{filtered.slice(range.start, range.end).map(member => <li key={member.user_id}>
        <MemberDialog member={member} workspaceId={workspaceId} workspaceName={workspaceName} csrfToken={session.csrf_token} self={member.user_id === session.user_id} onChanged={onChanged} onRequestFailed={onRequestFailed}
          trigger={<button type="button" className="people-row" aria-label={`View ${member.email}${member.user_id === session.user_id ? ' (you)' : ''}`}>
            <span className="people-avatar" aria-hidden="true">{memberInitials(member.email)}</span><span className="people-row-copy"><strong>{member.email}{member.user_id === session.user_id && <span className="people-you">You</span>}</strong>
              <span className={`people-access is-${memberStatus(member)}`}><i aria-hidden="true" />{memberStatusLabel[memberStatus(member)]}</span></span>
            <span className="people-role-label">{memberRoles[member.role].label}</span><ChevronRight size={15} aria-hidden="true" />
          </button>} />
      </li>)}</ul> : <div className="people-empty"><Users size={25} strokeWidth={1.4} aria-hidden="true" /><h3>{hasFilters ? 'No members match' : view === 'inactive' ? 'Everyone has access' : 'No active members'}</h3>
        <p>{hasFilters ? 'Try another email or show all roles.' : view === 'inactive' ? 'Revoked memberships and disabled accounts will appear here.' : 'Invite someone to start working together.'}</p>
        {hasFilters && <button type="button" className="people-button" onClick={reset}>Clear filters</button>}
      </div>}
      {filtered.length > 12 && <ListPagination page={range.page} total={filtered.length} pageSize={12} label="Members" onPrevious={() => { setPagination({ view, page: range.page - 1 }); heading.current?.focus() }} onNext={() => { setPagination({ view, page: range.page + 1 }); heading.current?.focus() }} />}
      <p className="people-footnote">Workspace access is separate from access to individual documents.</p>
    </Tabs.Content>
  </Tabs.Root>
}
