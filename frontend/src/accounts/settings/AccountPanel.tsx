import { useState } from 'react'
import { ChevronRight, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { SessionView } from '../../api/client'
import { GlassInput } from '../../ui/GlassField'
import { ListPagination } from '../../ui/ListPagination'
import { pageWindow } from '../../ui/pagination'
import { EmailVerification } from './EmailVerification'
import { memberInitials } from './memberPresentation'

export function AccountPanel({ session, onSessionChanged }: { session: SessionView; onSessionChanged: (session: SessionView) => void }) {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const memberships = session.memberships.filter(item => `${item.workspace_name} ${item.role}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  const range = pageWindow(memberships.length, page, 5)
  return <>
    <section className="settings-section" aria-labelledby="account-profile-title"><div className="settings-account-identity"><span aria-hidden="true">{memberInitials(session.email)}</span><div><h3 id="account-profile-title">Your profile</h3><p>Your account is identified by your sign-in email.</p></div></div><EmailVerification session={session} onVerified={onSessionChanged} /></section>
    <section className="settings-section" aria-labelledby="account-workspaces-title"><header className="settings-section-heading"><h3 id="account-workspaces-title">Workspace memberships</h3><p>Your role and document access are managed separately in each workspace.</p></header>
      {session.memberships.length > 5 && <GlassInput type="search" icon={Search} aria-label="Find a workspace" placeholder="Find a workspace…" value={search} maxLength={200} onChange={event => { setSearch(event.target.value); setPage(0) }} />}
      <ul className="settings-memberships">{memberships.slice(range.start, range.end).map(item => <li key={item.workspace_id}><Link to={`/?workspace=${encodeURIComponent(item.workspace_id)}`} aria-label={`Open ${item.workspace_name || 'workspace'}`}><span><strong>{item.workspace_name || 'Workspace'}</strong><small>{item.role === 'administrator' ? 'Administrator' : 'Member'}</small></span><ChevronRight size={15} aria-hidden="true" /></Link></li>)}</ul>
      {!memberships.length && <p className="settings-help" role="status">{search.trim() ? 'No matching workspaces. Try another name or role.' : 'You have no active workspace access.'}</p>}
      {session.memberships.length > 5 && <ListPagination page={range.page} total={memberships.length} pageSize={5} label="Workspaces" onPrevious={() => setPage(range.page - 1)} onNext={() => setPage(range.page + 1)} />}
    </section>
  </>
}
