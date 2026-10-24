import { useEffect } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { useReviewWorkspace } from '../resume/reviewWorkspace'
import { Brand } from '../ui/Brand'
import { workspaceHref } from './navigation'
import './not-found.css'

export function NotFoundPage({ session }: { session?: SessionView }) {
  const { search } = useLocation()
  const preferred = useReviewWorkspace(session?.user_id ?? '')
  const requested = new URLSearchParams(search).get('workspace')
  const workspace = session?.memberships.find(item => item.workspace_id === requested)
    ?? session?.memberships.find(item => item.workspace_id === preferred) ?? session?.memberships[0]
  useEffect(() => {
    const previousTitle = document.title
    document.title = 'Page not found · OpenAnonymi'
    return () => { document.title = previousTitle }
  }, [])
  const content = (
    <section className="not-found-page" aria-labelledby="not-found-title">
      <div className="not-found-copy">
        <p className="not-found-eyebrow"><span>404</span> Page unavailable</p>
        <h1 id="not-found-title">Page not found</h1>
        <p className="not-found-description">
          This link doesn’t lead to a page in OpenAnonymi.
          The address may be incomplete, or the page may have moved.
        </p>
        <div className="not-found-actions">
          <Link className="button-primary" to={session ? workspaceHref('/documents', workspace?.workspace_id) : '/sign-in'}>
            {session ? 'Go to documents' : 'Sign in to your workspace'}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
          <Link className="not-found-secondary" to={session ? workspaceHref('/', workspace?.workspace_id) : '/welcome'}>
            {session ? 'Open overview' : 'Visit homepage'}
          </Link>
        </div>
        <div className="not-found-help">
          <h2>Following a shared link?</h2>
          <p>Ask the sender for the complete, up-to-date address.</p>
        </div>
      </div>
    </section>
  )

  return session ? content : (
    <div className="not-found-public">
      <header>
        <Link to="/welcome" aria-label="OpenAnonymi home">
          <Brand />
        </Link>
      </header>
      <main id="main-content">{content}</main>
    </div>
  )
}
