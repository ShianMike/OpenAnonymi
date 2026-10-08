import { useState, type RefObject } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ChevronDown, ShieldCheck, SlidersHorizontal, FolderOpen, Sparkles, X } from 'lucide-react'
import type { SessionView } from '../api/client'
import { Brand } from '../ui/Brand'
import { pages } from './navigation'
import { ResumeReviewLink } from '../resume/ResumeReviewLink'
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
  const { pathname } = useLocation()
  const workspace = session.memberships.length === 1 ? session.memberships[0] : null
  const label = workspace?.workspace_name ?? `${session.memberships.length} workspaces`
  const sections = [
    { title: 'Workspace', icon: FolderOpen, entries: pages.slice(0, 3) },
    { title: 'Manage', icon: SlidersHorizontal, entries: pages.slice(3).filter((page) => page.path !== '/preferences') },
  ]
  return (
    <aside
      className={`app-sidebar${menuOpen ? ' is-open' : ''}`}
      id="app-sidebar"
      role={menuOpen ? 'dialog' : undefined}
      aria-modal={menuOpen ? true : undefined}
      aria-label="Workspace navigation"
      onKeyDown={(event) => {
        if (!menuOpen) return
        if (event.key === 'Escape') onClose()
        if (event.key === 'Tab') {
          const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('a, button')).filter(
            (item) => item.getClientRects().length > 0 && !item.matches(':disabled'),
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
        <span className="workspace-avatar" aria-hidden="true">
          {label.slice(0, 1).toUpperCase()}
        </span>
        <div>
          <strong title={label}>{label}</strong>
          <span>
            {workspace
              ? workspace.role === 'administrator'
                ? 'Your workspace · Admin'
                : 'Your workspace · Member'
              : 'Select a workspace on each page'}
          </span>
        </div>
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
            <div className="branch-children" id={`branch-${title}`} hidden={collapsed[title]}>
              {entries.map((page) => {
                const active = page.path === '/' ? pathname === '/' : pathname.startsWith(page.path)
                return (
                  <NavLink
                    key={page.path}
                    to={page.path}
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
              {title === 'Workspace' && <ResumeReviewLink onClick={onClose} />}
            </div>
          </div>
        ))}
      </nav>
      <div className="sidebar-note">
        <Sparkles size={19} strokeWidth={1.5} aria-hidden="true" />
        <p>
          A little care.
          <br />
          <strong>A lot more privacy.</strong>
        </p>
        <span>Review every finding before sharing.</span>
      </div>
      <div className="sidebar-footer">
        <ShieldCheck size={14} aria-hidden="true" />
        <span>Your review. Your call.</span>
      </div>
    </aside>
  )
}
