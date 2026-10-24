import { useEffect, useState, type RefObject } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { Building2, Check, ChevronDown, ChevronRight, Monitor, Moon, Palette, Plus, SlidersHorizontal, Sun, X } from 'lucide-react'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { AppCredit } from '../ui/AppCredit'
import { pages, workspaceHref, workspacePages } from './navigation'
import { rememberReviewWorkspace, useReviewWorkspace } from '../resume/reviewWorkspace'
import { GlassSelect } from '../ui/GlassSelect'
import { useAppearance } from '../appearance/useAppearance'
import { QuickGuideButton } from '../onboarding/QuickGuide'
import './shell.css'

type Props = {
  session: SessionView
  menuOpen: boolean
  onClose: () => void
  navRef: RefObject<HTMLElement | null>
}

export function Sidebar({ session, menuOpen, onClose, navRef }: Props) {
  const { preference, setAppearance } = useAppearance()
  const themeLabel = { light: 'Light', dark: 'Dark', system: 'System' }[preference]
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
    { title: 'Workspace', entries: pages.slice(0, 3).filter(page => page.path !== '/new') },
    { title: 'Manage', entries: pages.slice(3).filter(page => page.path !== '/preferences' &&
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
      <Link to={workspaceHref('/', workspace?.workspace_id)} className="sidebar-brand" aria-label="OpenAnonymi overview" onClick={onClose}>
        <Brand />
      </Link>
      <div className="workspace-context">
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
      {workspace && <Link className="sidebar-create" to={workspaceHref('/new', workspace.workspace_id)} onClick={onClose}>
        <Plus size={17} aria-hidden="true" /> New review
      </Link>}
      <nav className="app-nav" aria-label="Main navigation" ref={navRef}>
        {sections.map(({ title, entries }) => (
          <div className="nav-group" key={title}>
            <h2 className="nav-group-title">{title}</h2>
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
                    <page.icon size={16} strokeWidth={1.7} aria-hidden="true" />
                    <span>{page.name}</span>
                  </NavLink>
                )
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <QuickGuideButton className="sidebar-footer-action" onClick={onClose} />
        <Menu.Root modal={false}>
          <Menu.Trigger className="sidebar-footer-action" aria-label={`Appearance: ${themeLabel}`}>
            <Palette size={16} strokeWidth={1.7} aria-hidden="true" /><span>Appearance</span>
            <small>{themeLabel}</small><ChevronDown size={13} aria-hidden="true" />
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Content className="app-credit-menu sidebar-appearance-menu" side="top" align="start" sideOffset={8} collisionPadding={12} aria-label="Appearance">
              <Menu.Label className="sidebar-appearance-label">Color theme</Menu.Label>
              <Menu.RadioGroup value={preference} aria-label="Color theme">
                {([{ value: 'light', label: 'Light', icon: Sun }, { value: 'dark', label: 'Dark', icon: Moon }, { value: 'system', label: 'System', icon: Monitor }] as const).map(({ value, label, icon: Icon }) =>
                  <Menu.RadioItem key={value} value={value} onSelect={() => setAppearance(value)}>
                    <Icon size={16} strokeWidth={1.7} aria-hidden="true" /><span className="sidebar-theme-label">{label}</span>
                    <Menu.ItemIndicator><Check size={15} aria-hidden="true" /></Menu.ItemIndicator>
                  </Menu.RadioItem>)}
              </Menu.RadioGroup>
              <Menu.Separator className="app-credit-separator" />
              <Menu.Item asChild><Link to="/preferences" onClick={onClose}>
                <SlidersHorizontal size={16} strokeWidth={1.7} aria-hidden="true" /><span className="sidebar-theme-label">Display preferences</span><ChevronRight size={13} aria-hidden="true" />
              </Link></Menu.Item>
            </Menu.Content>
          </Menu.Portal>
        </Menu.Root>
        <AppCredit sidebar />
      </div>
    </aside>
  )
}
