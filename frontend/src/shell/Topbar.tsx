import { lazy, Suspense, useRef, type RefObject } from 'react'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { ChevronDown, ChevronRight, LogOut, Menu as MenuIcon, Palette, Settings2, ShieldCheck, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { NotificationLink } from '../notifications/NotificationLink'
import { useReviewWorkspace } from '../resume/reviewWorkspace'
import { memberInitials } from '../accounts/settings/memberPresentation'
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
  const initials = memberInitials(session.email)
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
        <Menu.Trigger ref={accountButtonRef} className="topbar-profile" aria-label="Account menu" title={session.email} disabled={signOutPending}>
          <span className="topbar-avatar" aria-hidden="true">{initials}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content className="topbar-account-menu" align="end" sideOffset={8} collisionPadding={12} aria-label="Your account"
            onCloseAutoFocus={(event) => {
              if (openingConfirmation.current) {
                event.preventDefault()
                openingConfirmation.current = false
              }
            }}>
            <Menu.Label className="topbar-account-summary">
              <span className="topbar-avatar" aria-hidden="true">{initials}</span>
              <span><small>Signed in as</small><strong>{session.email}</strong></span>
            </Menu.Label>
            <Menu.Group className="topbar-account-links" aria-label="Personal settings">
              <Menu.Item asChild textValue="Account settings"><Link to="/settings?section=account"><Settings2 size={17} strokeWidth={1.6} aria-hidden="true" /><span><strong>Account settings</strong><small>Email and workspace memberships</small></span><ChevronRight className="topbar-account-arrow" size={14} aria-hidden="true" /></Link></Menu.Item>
              <Menu.Item asChild textValue="Security"><Link to="/settings?section=security"><ShieldCheck size={17} strokeWidth={1.6} aria-hidden="true" /><span><strong>Security</strong><small>Password and two-step verification</small></span><ChevronRight className="topbar-account-arrow" size={14} aria-hidden="true" /></Link></Menu.Item>
              <Menu.Item asChild textValue="Appearance & preferences"><Link to="/settings?section=appearance"><Palette size={17} strokeWidth={1.6} aria-hidden="true" /><span><strong>Appearance & preferences</strong><small>Theme, text size and motion</small></span><ChevronRight className="topbar-account-arrow" size={14} aria-hidden="true" /></Link></Menu.Item>
            </Menu.Group>
            <Menu.Separator className="topbar-menu-separator" />
            <Menu.Item className="topbar-signout" textValue="Sign out" disabled={signOutPending} onSelect={() => {
              openingConfirmation.current = true
              onSignOut()
            }}><LogOut size={17} strokeWidth={1.6} aria-hidden="true" /><span><strong>{signOutPending ? 'Signing out…' : 'Sign out'}</strong><small>End this browser session</small></span></Menu.Item>
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
    </div>
  </header>
}
