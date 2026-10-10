import { useEffect, useState, type RefObject } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Building2, ChevronDown, ShieldCheck, SlidersHorizontal, FolderOpen, X } from 'lucide-react'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { AppCredit } from '../ui/AppCredit'
import { pages, workspaceHref, workspacePages } from './navigation'
import { ResumeReviewLink } from '../resume/ResumeReviewLink'
import { rememberReviewWorkspace, useReviewWorkspace } from '../resume/reviewWorkspace'
import { GlassSelect } from '../ui/GlassSelect'
import { BranchCurve } from './BranchCurve'
import './shell.css'

type Props = {
  session: SessionView
  menuOpen: boolean
  onClose: () => void
  navRef: RefObject<HTMLElement | null>
}

export function Sidebar({ session, menuOpen, onClose, navRef }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    const viewport = window.matchMedia('(max-width: 900px)')
    const changed = () => setNarrow(viewport.matches)
    changed()
    viewport.addEventListener('change', changed)
    return () => viewport.removeEventListener('change', changed)
  }, [])
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const preferred = useReviewWorkspace(session.user_id)
  const requested = new URLSearchParams(search).get('workspace')
  const workspace = session.memberships.find(item => item.workspace_id === requested)
    ?? session.memberships.find(item => item.workspace_id === preferred) ?? session.memberships[0]
  const label = workspace?.workspace_name || 'No active workspace'
  useEffect(() => {
    if (workspace && requested === workspace.workspace_id) rememberReviewWorkspace(session.user_id, workspace.workspace_id)
  }, [session.user_id, requested, workspace])
  const sections = [
    { title: 'Workspace', icon: FolderOpen, entries: pages.slice(0, 3) },
    { title: 'Manage', icon: SlidersHorizontal, entries: pages.slice(3).filter(page => page.path !== '/preferences' &&
      (page.path !== '/members' || session.memberships.some(item => item.role === 'administrator'))) },
  ]
  return (
    <aside
      className={`app-sidebar${menuOpen ? ' is-open' : ''}`}
      id="app-sidebar"
      role={narrow && menuOpen ? 'dialog' : undefined}
      aria-modal={narrow && menuOpen ? true : undefined}
      aria-label="Workspace navigation"
      aria-hidden={narrow && !menuOpen ? true : undefined}
      inert={narrow && !menuOpen}
      onKeyDown={(event) => {
        if (!menuOpen) return
        if (event.key === 'Escape') onClose()
        if (event.key === 'Tab') {
          const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('a, button')).filter(
            (item) => item.getClientRects().length > 0 && !item.matches(':disabled') && !item.closest('[inert]'),
          )
          const first = controls[0]
          const last = controls[controls.length - 1]
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault()
            last?.focus()
          }
          if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault()
            first?.focus()
          }
        }
      }}
    >
      <button
        className="drawer-close icon-button"
        type="button"
        aria-label="Close navigation"
        onClick={onClose}
      >
        <X size={18} aria-hidden="true" />
      </button>
      <div className="sidebar-brand">
        <Brand />
      </div>
      <div className="workspace-context">
        <label htmlFor="sidebar-workspace">Workspace <span title="Available workspaces">{session.memberships.length}</span></label>
        {workspace ? <>
          <GlassSelect id="sidebar-workspace" aria-label="Switch workspace" value={workspace.workspace_id}
            displayValue={<span className="workspace-switcher-value"><span className="workspace-switcher-icon"><Building2 size={17} aria-hidden="true" /></span>
              <span className="workspace-switcher-copy"><strong>{label}</strong><small>{workspace.role === 'administrator' ? 'Administrator' : 'Member'}</small></span>
            </span>}
            onValueChange={id => {
              if (id === workspace.workspace_id) return
              const next = new URLSearchParams(search)
              next.set('workspace', id)
              const member = session.memberships.find(item => item.workspace_id === id)
              if (pathname === '/settings' && next.get('section') === 'retention' && member?.role !== 'administrator') next.set('section', 'account')
              const stay = workspacePages.includes(pathname) && pathname !== '/new' &&
                (pathname !== '/members' || member?.role === 'administrator')
              navigate(stay ? { pathname, search: next.toString() } : workspaceHref('/', id))
              onClose()
            }}>
            {session.memberships.map(item => <option key={item.workspace_id} value={item.workspace_id}
              data-description={item.role === 'administrator' ? 'Administrator' : 'Member'}>{item.workspace_name || 'Workspace'}</option>)}
          </GlassSelect>
        </> : <strong>{label}</strong>}
      </div>
      <nav className="app-nav" aria-label="Main navigation" ref={navRef}>
        {sections.map(({ title, icon: Icon, entries }) => (
          <div className="nav-branch" key={title}>
            <button
              type="button"
              className="branch-heading"
              aria-expanded={!collapsed[title]}
              aria-controls={`branch-${title}`}
              onClick={() => setCollapsed((current) => ({ ...current, [title]: !current[title] }))}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{title}</span>
              <ChevronDown size={13} aria-hidden="true" />
            </button>
            <div className="branch-children" id={`branch-${title}`} aria-hidden={!!collapsed[title]} inert={!!collapsed[title]}>
              <div className="branch-links">
              {entries.map((page) => {
                const active = page.path === '/' ? pathname === '/' : pathname.startsWith(page.path)
                return (
                  <NavLink
                    key={page.path}
                    to={workspaceHref(page.path, workspace?.workspace_id)}
                    end={page.path === '/'}
                    className={active ? 'branch-link is-active' : 'branch-link'}
                    onClick={onClose}
                  >
                    <BranchCurve />
                    <page.icon size={16} strokeWidth={1.7} aria-hidden="true" />
                    <span>{page.name}</span>
                    {active && <span className="branch-active-dot" aria-hidden="true" />}
                  </NavLink>
                )
              })}
              {title === 'Workspace' && <ResumeReviewLink workspaceId={workspace?.workspace_id} onClick={onClose} />}
              </div>
            </div>
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-note">
          <ShieldCheck size={18} strokeWidth={1.6} aria-hidden="true" />
          <div><strong>Share with care</strong><p>Read the reviewed text before you share.</p></div>
        </div>
        <AppCredit />
      </div>
    </aside>
  )
}
