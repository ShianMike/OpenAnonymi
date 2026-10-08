import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, matchPath, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { SignOutDialog } from './accounts/SignOutDialog'
import { ApiRequestError, getSession, signOut, type SessionView } from './api/client'
import { Sidebar } from './shell/Sidebar'
import { Topbar } from './shell/Topbar'
import { pages } from './shell/navigation'
import { useAppearance } from './appearance/useAppearance'
import { useDisplayPreferences } from './appearance/useDisplayPreferences'
import { authDestination } from './accounts/authNavigation'
import { LoadingScreen } from './loading/LoadingScreen'
import { RouteLoading } from './loading/RouteLoading'
import { PageLoadBoundary } from './loading/PageLoadBoundary'
import { LoadingFailure } from './loading/LoadingFailure'
import { SESSION_ENDED_EVENT, matchesSessionScope, reportEndedScope, setSessionScope } from './api/sessionEvents'
import { protectReviewCacheLifecycle } from './api/reviewCache'
import './App.css'

const SignInPage = lazy(() => import('./accounts/SignInPage').then((module) => ({ default: module.SignInPage })))
const SettingsPage = lazy(() => import('./accounts/SettingsPage').then((module) => ({ default: module.SettingsPage })))
const MembersPage = lazy(() => import('./accounts/MembersPage').then((module) => ({ default: module.MembersPage })))
const NewReviewPage = lazy(() => import('./review/NewReviewPage').then((module) => ({ default: module.NewReviewPage })))
const ActivityPage = lazy(() => import('./workspace/ActivityPage').then((module) => ({ default: module.ActivityPage })))
const OverviewPage = lazy(() => import('./workspace/OverviewPage').then((module) => ({ default: module.OverviewPage })))
const RulesPage = lazy(() => import('./workspace/RulesPage').then((module) => ({ default: module.RulesPage })))
const HistoryPage = lazy(() => import('./workspace/HistoryPage').then((module) => ({ default: module.HistoryPage })))
const EditDraftPage = lazy(() =>
  import('./review/EditDraftPage').then((module) => ({ default: module.EditDraftPage })),
)
const NotificationsPage = lazy(() => import('./notifications/NotificationsPage').then((module) => ({ default: module.NotificationsPage })))
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
  useDisplayPreferences()
  useEffect(protectReviewCacheLifecycle, [])
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
  const accountButtonRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const previousPathRef = useRef(pathname)
  const authenticationScope = authentication.kind === 'signed-in' ? authentication.session.csrf_token : ''
  const sessionExpires = authentication.kind === 'signed-in' ? authentication.session.expires_at : ''
  useEffect(() => {
    if (!authenticationScope || !sessionExpires) return
    const remaining = Date.parse(sessionExpires) - Date.now()
    if (!Number.isFinite(remaining)) return
    const timer = setTimeout(() => reportEndedScope(authenticationScope), Math.max(0, remaining))
    return () => clearTimeout(timer)
  }, [authenticationScope, sessionExpires])

  useEffect(() => {
    const scope = authenticationScope
    setSessionScope(scope)
    function sessionEnded(event: Event) {
      if (!matchesSessionScope(event, scope)) return
      setAuthentication((current) => {
        if (current.kind !== 'signed-in' || current.session.csrf_token !== scope) return current
        return { kind: 'signed-out' }
      })
      setSignInNotice('Your session has ended. Sign in again to continue.')
      setUnsavedPage(false)
      setSignOutConfirm(false)
      setMenuOpen(false)
    }
    window.addEventListener(SESSION_ENDED_EVENT, sessionEnded)
    return () => { window.removeEventListener(SESSION_ENDED_EVENT, sessionEnded) }
  }, [authenticationScope])

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

  const handleUnsavedChange = useCallback((dirty: boolean) => {
    setUnsavedPage(dirty)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal)
      .then((session) => {
        if (!controller.signal.aborted) {
          setSessionScope(session.csrf_token)
          setAuthentication({ kind: 'signed-in', session })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (error instanceof ApiRequestError && error.status === 401) {
          setSessionScope('')
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
    if (!signedIn || !authenticationScope) return
    const scope = authenticationScope
    const controller = new AbortController()
    function refreshSession() {
      if (document.visibilityState !== 'visible') return
      getSession(controller.signal).then((session) => {
        if (!controller.signal.aborted) setAuthentication((current) =>
          current.kind === 'signed-in' && current.session.csrf_token === scope &&
          current.session.user_id === session.user_id && session.csrf_token === scope
            ? { kind: 'signed-in', session } : current)
      }).catch(() => { /* The next authenticated action reports a session failure. */ })
    }
    refreshSession()
    document.addEventListener('visibilitychange', refreshSession)
    window.addEventListener('focus', refreshSession)
    return () => { controller.abort(); document.removeEventListener('visibilitychange', refreshSession); window.removeEventListener('focus', refreshSession) }
  }, [pathname, signedIn, authenticationScope])

  function handleSignOut() {
    if (authentication.kind !== 'signed-in' || signOutPending) return
    setSignOutError(null)
    setSignOutConfirm(true)
  }

  async function performSignOut() {
    if (authentication.kind !== 'signed-in' || signOutPending) return
    setSignOutPending(true)
    setSignOutError(null)
    try {
      await signOut(authentication.session.csrf_token)
      setSignOutConfirm(false)
      setUnsavedPage(false)
      setSessionScope('')
      setAuthentication({ kind: 'signed-out' })
    } catch (error: unknown) {
      setSignOutError(error instanceof ApiRequestError && error.status < 500 ? error.message
        : 'We couldn’t confirm sign-out. Check your connection and try again.')
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
      <LoadingScreen label="Checking your session…" description="Checking access before opening your workspace." />
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
            <LoadingScreen label="Opening the page…" description="Preparing your next step." />
          }
        >
          <NotFoundPage signedOut />
        </Suspense></PageLoadBoundary>
      )
    }
    return (
      <PageLoadBoundary key={pathname} fullScreen><Suspense fallback={<LoadingScreen label="Opening sign in…" description="Preparing secure access to your workspace." />}><SignInPage
        key={pathname}
        initialMode={pathname === '/sign-up' ? 'sign-up' : 'sign-in'}
        notice={signInNotice}
        onSignedIn={(session, creatingAccount) => {
          setSessionScope(session.csrf_token)
          setSignInNotice(null)
          setAuthentication({ kind: 'signed-in', session })
          if (authRoute) navigate(authDestination(search, creatingAccount), { replace: true })
        }}
      /></Suspense></PageLoadBoundary>
    )
  }
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
        <Topbar session={authentication.session} title={pageTitle} menuOpen={menuOpen}
          menuButtonRef={menuButtonRef} accountButtonRef={accountButtonRef}
          onMenuToggle={() => setMenuOpen((value) => !value)} onSignOut={handleSignOut} signOutPending={signOutPending} />
        <SignOutDialog
          open={signOutConfirm}
          pending={signOutPending}
          unsaved={unsavedPage}
          error={signOutError}
          onStay={() => { setSignOutConfirm(false); setSignOutError(null) }}
          restoreFocus={() => accountButtonRef.current?.focus()}
          onConfirm={() => void performSignOut()}
        />
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
              <Route path="/notifications" element={<NotificationsPage key={authentication.session.user_id} session={authentication.session} />} />
              <Route path="/continue" element={<ContinueReviewPage session={authentication.session} />} />
              <Route path="/activity" element={<ActivityPage session={authentication.session} />} />
              <Route path="/members" element={<MembersPage session={authentication.session} />} />
              <Route path="/rules" element={<RulesPage session={authentication.session} />} />
              <Route path="/preferences" element={<PreferencesPage />} />
              <Route
                path="/documents/:documentId/edit"
                element={
                  <EditDraftPage key={`${authentication.session.csrf_token}:${pathname}`} session={authentication.session} onUnsavedChange={handleUnsavedChange} />
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
                    onSessionChanged={(session) => { setSessionScope(session.csrf_token); setAuthentication({ kind: 'signed-in', session }) }}
                    onSignedOut={() => { setSessionScope(''); setSignInNotice('Session signed out. Sign in again to continue.'); setAuthentication({ kind: 'signed-out' }) }}
                    onPasswordChanged={() => {
                      setSessionScope('')
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
