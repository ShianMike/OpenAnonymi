import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { SignInPage } from './accounts/SignInPage'
import { SettingsPage } from './accounts/SettingsPage'
import { EditDraftPage } from './review/EditDraftPage'
import { NewReviewPage } from './review/NewReviewPage'
import { ActivityPage } from './workspace/ActivityPage'
import { DocumentsPage } from './workspace/DocumentsPage'
import { OverviewPage } from './workspace/OverviewPage'
import { RulesPage } from './workspace/RulesPage'
import {
  ApiRequestError, getSession, signOut, type SessionView,
} from './api/client'
import './App.css'

const pages = [
  { path: '/', name: 'Overview' },
  { path: '/new', name: 'New review' },
  { path: '/documents', name: 'Documents' },
  { path: '/rules', name: 'Rules' },
  { path: '/activity', name: 'Activity' },
  { path: '/settings', name: 'Settings' },
]

type Authentication =
  | { kind: 'checking' }
  | { kind: 'signed-out' }
  | { kind: 'error'; message: string }
  | { kind: 'signed-in'; session: SessionView }

function PendingPage({ title }: { title: string }) {
  return (
    <section>
      <h1>{title}</h1>
      <p>This part of the review workflow is not available yet.</p>
    </section>
  )
}

function App() {
  const [authentication, setAuthentication] = useState<Authentication>({ kind: 'checking' })
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [signOutPending, setSignOutPending] = useState(false)

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
      <div className="app">
        <header className="app-header"><strong>OpenAnonymi</strong><span>Privacy review</span></header>
        <SignInPage onSignedIn={(session) => setAuthentication({ kind: 'signed-in', session })} />
      </div>
    )
  }
  return (
    <div className="app">
      <header className="app-header">
        <strong>OpenAnonymi</strong>
        <span>Privacy review</span>
        <span>Signed in as {authentication.session.email}</span>
        <button type="button" onClick={handleSignOut} disabled={signOutPending}>
          {signOutPending ? 'Signing out…' : 'Sign out'}
        </button>
      </header>
      {signOutError && <p role="alert">{signOutError}</p>}
      <div className="app-body">
        <nav aria-label="Main navigation">
          {pages.map((page) => (
            <NavLink key={page.path} to={page.path} end={page.path === '/'}>
              {page.name}
            </NavLink>
          ))}
        </nav>
        <main id="main-content">
          <Routes>
            <Route path="/" element={<OverviewPage session={authentication.session} />} />
            <Route path="/new" element={<NewReviewPage session={authentication.session} />} />
            <Route path="/documents" element={<DocumentsPage session={authentication.session} />} />
            <Route path="/activity" element={<ActivityPage session={authentication.session} />} />
            <Route path="/rules" element={<RulesPage session={authentication.session} />} />
            <Route path="/documents/:documentId/edit" element={<EditDraftPage session={authentication.session} />} />
            <Route path="/settings" element={<SettingsPage session={authentication.session} />} />
            {pages.slice(1).filter((page) => !['/new', '/documents', '/rules', '/activity', '/settings'].includes(page.path)).map((page) => (
              <Route key={page.path} path={page.path} element={<PendingPage title={page.name} />} />
            ))}
            <Route path="*" element={<PendingPage title="Page not found" />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
