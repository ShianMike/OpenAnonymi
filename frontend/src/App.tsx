import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  Activity, ChevronRight, FilePlus2, Files, LayoutDashboard,
  LogOut, Menu, Settings2, ShieldCheck, SlidersHorizontal, X,
} from 'lucide-react'
import { SignInPage } from './accounts/SignInPage'
import { SettingsPage } from './accounts/SettingsPage'
import { EditDraftPage } from './review/EditDraftPage'
import { NewReviewPage } from './review/NewReviewPage'
import { ActivityPage } from './workspace/ActivityPage'
import { DocumentsPage } from './workspace/DocumentsPage'
import { OverviewPage } from './workspace/OverviewPage'
import { RulesPage } from './workspace/RulesPage'
import { HistoryPage } from './workspace/HistoryPage'
import {
  ApiRequestError, getSession, signOut, type SessionView,
} from './api/client'
import './App.css'

const pages = [
  { path: '/', name: 'Overview', icon: LayoutDashboard },
  { path: '/new', name: 'New review', icon: FilePlus2 },
  { path: '/documents', name: 'Documents', icon: Files },
  { path: '/rules', name: 'Rules', icon: SlidersHorizontal },
  { path: '/activity', name: 'Activity', icon: Activity },
  { path: '/settings', name: 'Settings', icon: Settings2 },
]

type Authentication =
  | { kind: 'checking' }
  | { kind: 'signed-out' }
  | { kind: 'error'; message: string }
  | { kind: 'signed-in'; session: SessionView }

function NotFoundPage() {
  return (
    <section>
      <h1>Page not found</h1>
      <p>That page could not be found in this workspace.</p>
      <Link to="/">Back to Overview</Link>
    </section>
  )
}

function App() {
  const { pathname } = useLocation()
  const [authentication, setAuthentication] = useState<Authentication>({ kind: 'checking' })
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [signOutPending, setSignOutPending] = useState(false)
  const [signInNotice, setSignInNotice] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const previousPathRef = useRef(pathname)

  const activePage = pages.find((page) => page.path === pathname)
  const pageTitle = activePage?.name ??
    (pathname.endsWith('/history') ? 'Review history' :
      pathname.endsWith('/edit') ? 'Review workspace' : 'Page not found')

  useEffect(() => {
    if (previousPathRef.current !== pathname) {
      previousPathRef.current = pathname
      mainRef.current?.focus()
    }
  }, [pathname])

  useEffect(() => {
    if (menuOpen) navRef.current?.querySelector('a')?.focus()
  }, [menuOpen])

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal).then((session) => {
      if (!controller.signal.aborted) setAuthentication({ kind: 'signed-in', session })
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return
      if (error instanceof ApiRequestError && error.status === 401) {
        setAuthentication({ kind: 'signed-out' })
      } else {
        setAuthentication({
          kind: 'error',
          message: error instanceof Error ? error.message : 'The session could not be checked.',
        })
      }
    })
    return () => controller.abort()
  }, [sessionAttempt])

  async function handleSignOut() {
    if (authentication.kind !== 'signed-in') return
    setSignOutPending(true)
    setSignOutError(null)
    try {
      await signOut(authentication.session.csrf_token)
      setAuthentication({ kind: 'signed-out' })
    } catch (error: unknown) {
      setSignOutError(error instanceof Error ? error.message : 'Sign-out failed. Try again.')
    } finally {
      setSignOutPending(false)
    }
  }

  if (authentication.kind === 'checking') {
    return <main id="main-content"><p role="status">Checking your session…</p></main>
  }
  if (authentication.kind === 'error') {
    return (
      <main id="main-content">
        <p role="alert">{authentication.message}</p>
        <button type="button" onClick={() => {
          setAuthentication({ kind: 'checking' })
          setSessionAttempt((value) => value + 1)
        }}>Retry</button>
      </main>
    )
  }
  if (authentication.kind === 'signed-out') {
    return (
      <div className="app auth-shell">
        <header className="auth-brand"><span className="brand-mark" aria-hidden="true">O</span>
          <strong>OpenAnonymi</strong><span>Privacy review</span></header>
        {signInNotice && <p role="status">{signInNotice}</p>}
        <SignInPage onSignedIn={(session) => {
          setSignInNotice(null)
          setAuthentication({ kind: 'signed-in', session })
        }} />
      </div>
    )
  }
  const currentWorkspace = authentication.session.memberships.length === 1
    ? authentication.session.memberships[0] : null
  const workspaceLabel = currentWorkspace?.workspace_name ??
    `${authentication.session.memberships.length} workspaces`
  return (
    <div className="app app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={`app-sidebar${menuOpen ? ' is-open' : ''}`} id="app-sidebar"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen) {
            setMenuOpen(false)
            menuButtonRef.current?.focus()
          }
        }}>
        <div className="sidebar-brand"><span className="brand-mark" aria-hidden="true">O</span>
          <span><strong>OpenAnonymi</strong><small>Privacy review</small></span></div>
        <div className="workspace-context">
          <span className="eyebrow">Workspace</span>
          <strong title={workspaceLabel}>
            {workspaceLabel}
          </strong>
          <span>{currentWorkspace
            ? currentWorkspace.role === 'administrator' ? 'Administrator' : 'Member'
            : 'Choose a workspace on each page'}</span>
        </div>
        <nav className="app-nav" aria-label="Main navigation" ref={navRef}>
          <span className="nav-heading">Workspace</span>
          {pages.map((page) => (
            <NavLink key={page.path} to={page.path} end={page.path === '/'}
              onClick={() => setMenuOpen(false)}>
              <page.icon size={17} strokeWidth={1.9} aria-hidden="true" />
              {page.name}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer"><ShieldCheck size={16} aria-hidden="true" />
          <span>Review before sharing</span></div>
      </aside>
      {menuOpen && <button className="nav-scrim" type="button" aria-label="Close navigation"
        onClick={() => {
          setMenuOpen(false)
          menuButtonRef.current?.focus()
        }} />}
      <div className="app-workarea">
        <header className="app-topbar">
          <button className="menu-toggle icon-button" type="button" ref={menuButtonRef}
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-controls="app-sidebar" aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}>
            {menuOpen ? <X size={19} aria-hidden="true" /> : <Menu size={19} aria-hidden="true" />}
          </button>
          <div className="breadcrumbs" aria-label="Current page">
            <span>{workspaceLabel}</span>
            <ChevronRight size={15} aria-hidden="true" />
            <strong>{pageTitle}</strong>
          </div>
          <div className="topbar-account"><span title={authentication.session.email}>
            {authentication.session.email}</span>
            <button className="text-button" type="button" aria-label="Sign out"
              onClick={handleSignOut}
              disabled={signOutPending}>
              <LogOut size={16} aria-hidden="true" />
              {signOutPending ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        </header>
        {signOutError && <p role="alert" className="topbar-alert">{signOutError}</p>}
        <main id="main-content" ref={mainRef} tabIndex={-1}>
          <Routes>
            <Route path="/" element={<OverviewPage session={authentication.session} />} />
            <Route path="/new" element={<NewReviewPage session={authentication.session} />} />
            <Route path="/documents" element={<DocumentsPage session={authentication.session} />} />
            <Route path="/activity" element={<ActivityPage session={authentication.session} />} />
            <Route path="/rules" element={<RulesPage session={authentication.session} />} />
            <Route path="/documents/:documentId/edit" element={<EditDraftPage session={authentication.session} />} />
            <Route path="/workspaces/:workspaceId/documents/:documentId/history" element={<HistoryPage />} />
            <Route path="/settings" element={<SettingsPage session={authentication.session}
              onPasswordChanged={() => {
                setSignInNotice('Password changed. Sign in again with your new password.')
                setAuthentication({ kind: 'signed-out' })
              }} />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
