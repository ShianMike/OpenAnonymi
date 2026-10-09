import { lazy, Suspense, useRef, type RefObject } from 'react'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { ChevronDown, ChevronRight, LogOut, Menu as MenuIcon, Palette, Settings2, ShieldCheck, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { NotificationLink } from '../notifications/NotificationLink'
import { useReviewWorkspace } from '../resume/reviewWorkspace'
import { workspacePages } from './navigation'

const GlobalSearch = lazy(() => import('../search/GlobalSearch').then((module) => ({ default: module.GlobalSearch })))

export function Topbar({ session, title, menuOpen, menuButtonRef, accountButtonRef, onMenuToggle, onSignOut, signOutPending }: {
  session: SessionView
  title: string
  menuOpen: boolean
  menuButtonRef: RefObject<HTMLButtonElement | null>
  accountButtonRef: RefObject<HTMLButtonElement | null>
  onMenuToggle: () => void
  onSignOut: () => void
  signOutPending: boolean
}) {
  const { pathname, search } = useLocation()
  const preferred = useReviewWorkspace(session.user_id)
  const workspace = session.memberships.find((item) => item.workspace_id === new URLSearchParams(search).get('workspace'))
    ?? (workspacePages.includes(pathname) ? session.memberships.find(item => item.workspace_id === preferred) : null)
    ?? (workspacePages.includes(pathname) || session.memberships.length === 1 ? session.memberships[0] : null)
  const workspaceLabel = workspace?.workspace_name ?? `${session.memberships.length} workspaces`
  const initials = session.email.split('@')[0].split(/[._+-]/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
  const openingConfirmation = useRef(false)
  return <header className="app-topbar">
    <button className="menu-toggle icon-button" type="button" ref={menuButtonRef}
      aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-controls="app-sidebar" aria-expanded={menuOpen}
      onClick={onMenuToggle}>
      {menuOpen ? <X size={20} aria-hidden="true" /> : <MenuIcon size={20} aria-hidden="true" />}
    </button>
    <nav className="topbar-context" aria-label="Current page">
      <Link className="topbar-workspace" to={workspace ? `/?workspace=${encodeURIComponent(workspace.workspace_id)}` : '/'}>
        {workspaceLabel}
      </Link>
      <ChevronRight size={14} aria-hidden="true" />
      <span className="topbar-page" aria-current="page">{title}</span>
    </nav>
    <div className="topbar-tools">
      <Suspense fallback={<span className="topbar-search-placeholder" aria-hidden="true" />}>
        <GlobalSearch key={session.user_id} session={session} />
      </Suspense>
      <NotificationLink key={session.user_id} userId={session.user_id} />
      <Menu.Root modal={false}>
        <Menu.Trigger ref={accountButtonRef} className="topbar-profile" aria-label="Account menu" disabled={signOutPending}>
          <span className="topbar-avatar" aria-hidden="true">{initials}</span>
          <span className="topbar-profile-label">My account</span>
          <ChevronDown size={14} aria-hidden="true" />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content className="topbar-account-menu" align="end" sideOffset={10} collisionPadding={12}
            onCloseAutoFocus={(event) => {
              if (openingConfirmation.current) {
                event.preventDefault()
                openingConfirmation.current = false
              }
            }}>
            <Menu.Label className="topbar-account-summary">
              <span className="topbar-avatar" aria-hidden="true">{initials}</span>
              <span><strong>Your account</strong><small>{session.email}</small></span>
            </Menu.Label>
            <Menu.Separator className="topbar-menu-separator" />
            <Menu.Item asChild><Link to="/settings?section=account"><Settings2 size={17} aria-hidden="true" /> Account settings</Link></Menu.Item>
            <Menu.Item asChild><Link to="/settings?section=security"><ShieldCheck size={17} aria-hidden="true" /> Security</Link></Menu.Item>
            <Menu.Item asChild><Link to="/preferences"><Palette size={17} aria-hidden="true" /> Appearance & preferences</Link></Menu.Item>
            <Menu.Separator className="topbar-menu-separator" />
            <Menu.Item className="topbar-signout" disabled={signOutPending} onSelect={() => {
              openingConfirmation.current = true
              onSignOut()
            }}><LogOut size={17} aria-hidden="true" /> Sign out</Menu.Item>
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
    </div>
  </header>
}
