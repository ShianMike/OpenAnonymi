import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, matchPath, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ChevronRight, LogOut, Menu, X } from 'lucide-react'
import { SignInPage } from './accounts/SignInPage'
import { SettingsPage } from './accounts/SettingsPage'
import { NewReviewPage } from './review/NewReviewPage'
import { ActivityPage } from './workspace/ActivityPage'
import { OverviewPage } from './workspace/OverviewPage'
import { RulesPage } from './workspace/RulesPage'
import { HistoryPage } from './workspace/HistoryPage'
import { ApiRequestError, getSession, signOut, type SessionView } from './api/client'
import { Sidebar } from './shell/Sidebar'
import { pages } from './shell/navigation'
import { useAppearance } from './appearance/useAppearance'
import { authDestination } from './accounts/authNavigation'
import { LoadingScreen } from './loading/LoadingScreen'
import { RouteLoading } from './loading/RouteLoading'
import { PageLoadBoundary } from './loading/PageLoadBoundary'
import { LoadingFailure } from './loading/LoadingFailure'
import './App.css'

const EditDraftPage = lazy(() =>
  import('./review/EditDraftPage').then((module) => ({ default: module.EditDraftPage })),
)
const DocumentsPage = lazy(() =>
  import('./workspace/DocumentsPage').then((module) => ({ default: module.DocumentsPage })),
)
const ContinueReviewPage = lazy(() =>
  import('./resume/ContinueReviewPage').then((module) => ({ default: module.ContinueReviewPage })),
)
const NotFoundPage = lazy(() =>
  import('./shell/NotFoundPage').then((module) => ({ default: module.NotFoundPage })),
)
const PreferencesPage = lazy(() =>
  import('./appearance/PreferencesPage').then((module) => ({ default: module.PreferencesPage })),
)
const LandingPage = lazy(() =>
  import('./landing/LandingPage').then((module) => ({ default: module.LandingPage })),
)

type Authentication =
  | { kind: 'checking' }
  | { kind: 'signed-out' }
  | { kind: 'error'; message: string }
  | { kind: 'signed-in'; session: SessionView }

function App() {
  useAppearance()
  useEffect(() => { document.getElementById('startup-loading')?.remove() }, [])
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const [authentication, setAuthentication] = useState<Authentication>({ kind: 'checking' })
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [signOutPending, setSignOutPending] = useState(false)
  const [unsavedPage, setUnsavedPage] = useState(false)
  const [signOutConfirm, setSignOutConfirm] = useState(false)
  const [signInNotice, setSignInNotice] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const signOutStayRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const previousPathRef = useRef(pathname)

  const activePage = pages.find((page) => page.path === pathname)
  const pageTitle =
    activePage?.name ?? (pathname === '/continue' ? 'Continue review' : undefined) ??
    (matchPath('/workspaces/:workspaceId/documents/:documentId/history', pathname)
      ? 'Review history'
      : matchPath('/documents/:documentId/edit', pathname)
        ? 'Review workspace'
        : 'Page not found')

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
    if (signOutConfirm) signOutStayRef.current?.focus()
  }, [signOutConfirm])

  const handleUnsavedChange = useCallback((dirty: boolean) => {
    setUnsavedPage(dirty)
    if (!dirty) setSignOutConfirm(false)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal)
      .then((session) => {
        if (!controller.signal.aborted) setAuthentication({ kind: 'signed-in', session })
      })
      .catch((error: unknown) => {
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

  const signedIn = authentication.kind === 'signed-in'
  useEffect(() => {
    if (!signedIn) return
    const controller = new AbortController()
    function refreshSession() {
      if (document.visibilityState !== 'visible') return
      getSession(controller.signal).then((session) => {
        if (!controller.signal.aborted) setAuthentication((current) =>
          current.kind === 'signed-in' && current.session.user_id === session.user_id
            ? { kind: 'signed-in', session } : current)
      }).catch(() => { /* The next authenticated action reports a session failure. */ })
    }
    refreshSession()
    document.addEventListener('visibilitychange', refreshSession)
    return () => { controller.abort(); document.removeEventListener('visibilitychange', refreshSession) }
  }, [pathname, signedIn])

  async function handleSignOut() {
    if (authentication.kind !== 'signed-in') return
    if (unsavedPage) {
      setSignOutConfirm(true)
      return
    }
    await performSignOut()
  }

  async function performSignOut() {
    if (authentication.kind !== 'signed-in') return
    setSignOutConfirm(false)
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

  const authRoute = pathname === '/sign-in' || pathname === '/sign-up'
  const publicLanding = pathname === '/welcome' || (pathname === '/' && authentication.kind !== 'signed-in')
  if (publicLanding) {
    return (
      <PageLoadBoundary key={pathname} fullScreen><Suspense fallback={<LoadingScreen label="Opening OpenAnonymi…" description="Preparing a little more privacy for your words." />}>
        <LandingPage
          signedIn={authentication.kind === 'signed-in'}
          sessionError={authentication.kind === 'error' ? authentication.message : undefined}
          onRetry={() => {
            setAuthentication({ kind: 'checking' })
            setSessionAttempt((value) => value + 1)
          }}
        />
      </Suspense></PageLoadBoundary>
    )
  }
  if (authRoute && authentication.kind === 'signed-in') {
    return <Navigate replace to={authDestination(search, pathname === '/sign-up')} />
  }
  if (authentication.kind === 'checking') {
    return (
      <LoadingScreen label="Checking your session…" description="Checking access before opening your workspace." shape="cards" />
    )
  }
  if (authentication.kind === 'error') {
    return (
      <LoadingFailure fullScreen title="We couldn’t check your session"
        message={authentication.message} onRetry={() => {
          setAuthentication({ kind: 'checking' })
          setSessionAttempt((value) => value + 1)
        }} />
    )
  }
  if (authentication.kind === 'signed-out') {
    const knownRoute =
      authRoute || pages.some((page) => matchPath(page.path, pathname)) ||
      matchPath('/continue', pathname) ||
      matchPath('/documents/:documentId/edit', pathname) ||
      matchPath('/workspaces/:workspaceId/documents/:documentId/history', pathname)
    if (!knownRoute) {
      return (
        <PageLoadBoundary key={pathname} fullScreen><Suspense
          fallback={
            <LoadingScreen label="Opening the page…" description="Preparing your next step." shape="cards" />
          }
        >
          <NotFoundPage signedOut />
        </Suspense></PageLoadBoundary>
      )
    }
    return (
      <SignInPage
        key={pathname}
        initialMode={pathname === '/sign-up' ? 'sign-up' : 'sign-in'}
        notice={signInNotice}
        onSignedIn={(session, creatingAccount) => {
          setSignInNotice(null)
          setAuthentication({ kind: 'signed-in', session })
          if (authRoute) navigate(authDestination(search, creatingAccount), { replace: true })
        }}
      />
    )
  }
  const currentWorkspace =
    authentication.session.memberships.length === 1 ? authentication.session.memberships[0] : null
  const workspaceLabel =
    currentWorkspace?.workspace_name ?? `${authentication.session.memberships.length} workspaces`
  return (
    <div className="app app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sidebar
        session={authentication.session}
        menuOpen={menuOpen}
        navRef={navRef}
        onClose={() => {
          setMenuOpen(false)
          if (menuOpen) menuButtonRef.current?.focus()
        }}
      />
      {menuOpen && (
        <button
          className="nav-scrim"
          type="button"
          aria-label="Close navigation"
          onClick={() => {
            setMenuOpen(false)
            menuButtonRef.current?.focus()
          }}
        />
      )}
      <div className="app-workarea">
        <header className="app-topbar">
          <button
            className="menu-toggle icon-button"
            type="button"
            ref={menuButtonRef}
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-controls="app-sidebar"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <X size={19} aria-hidden="true" /> : <Menu size={19} aria-hidden="true" />}
          </button>
          <div className="breadcrumbs" aria-label="Current page">
            <span>{workspaceLabel}</span>
            <ChevronRight size={15} aria-hidden="true" />
            <strong>{pageTitle}</strong>
          </div>
          <div className="topbar-account">
            <span title={authentication.session.email}>{authentication.session.email}</span>
            <button
              className="text-button"
              type="button"
              aria-label="Sign out"
              onClick={handleSignOut}
              disabled={signOutPending}
            >
              <LogOut size={16} aria-hidden="true" />
              {signOutPending ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        </header>
        {signOutError && (
          <p role="alert" className="topbar-alert">
            {signOutError}
          </p>
        )}
        {signOutConfirm && (
          <div className="signout-confirm surface-panel" role="alert">
            <strong>Unsaved changes</strong>
            <p>Signing out will discard your unsaved text and settings.</p>
            <button
              ref={signOutStayRef}
              type="button"
              onClick={() => {
                setSignOutConfirm(false)
                requestAnimationFrame(() =>
                  document.querySelector<HTMLElement>('#source-text, #source-file, #saved-source')?.focus(),
                )
              }}
            >
              Stay and keep editing
            </button>{' '}
            <button type="button" disabled={signOutPending} onClick={() => void performSignOut()}>
              Discard edits and sign out
            </button>
          </div>
        )}
        <main id="main-content" ref={mainRef} tabIndex={-1}>
          {authentication.session.second_factor_setup_required && <div className="security-requirement" role="status">
            A workspace requires two-step verification. <Link to="/settings?section=security">Set up your authenticator</Link>
          </div>}
          <PageLoadBoundary key={pathname}><Suspense fallback={<RouteLoading pathname={pathname} title={pageTitle} />}>
            <Routes>
              <Route path="/" element={<OverviewPage session={authentication.session} />} />
              <Route
                path="/new"
                element={
                  <NewReviewPage session={authentication.session} onUnsavedChange={handleUnsavedChange} />
                }
              />
              <Route path="/documents" element={<DocumentsPage session={authentication.session} />} />
              <Route path="/continue" element={<ContinueReviewPage session={authentication.session} />} />
              <Route path="/activity" element={<ActivityPage session={authentication.session} />} />
              <Route path="/rules" element={<RulesPage session={authentication.session} />} />
              <Route path="/preferences" element={<PreferencesPage />} />
              <Route
                path="/documents/:documentId/edit"
                element={
                  <EditDraftPage session={authentication.session} onUnsavedChange={handleUnsavedChange} />
                }
              />
              <Route
                path="/workspaces/:workspaceId/documents/:documentId/history"
                element={<HistoryPage />}
              />
              <Route
                path="/settings"
                element={
                  <SettingsPage
                    session={authentication.session}
                    onSessionChanged={(session) => setAuthentication({ kind: 'signed-in', session })}
                    onSignedOut={() => { setSignInNotice('Session signed out. Sign in again to continue.'); setAuthentication({ kind: 'signed-out' }) }}
                    onPasswordChanged={() => {
                      setSignInNotice('Password changed. Sign in again with your new password.')
                      setAuthentication({ kind: 'signed-out' })
                    }}
                  />
                }
              />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense></PageLoadBoundary>
        </main>
      </div>
    </div>
  )
}

export default App
