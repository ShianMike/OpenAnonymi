import { ArrowRight, ArrowUpRight, Files, LayoutDashboard } from 'lucide-react'
import { Link } from 'react-router-dom'
import { LostCompass } from './LostCompass'
import { Brand } from '../ui/Brand'
import './not-found.css'

export function NotFoundPage({ signedOut = false }: { signedOut?: boolean }) {
  const content = (
    <section className="not-found-page" aria-labelledby="not-found-title">
      <LostCompass />
      <div className="not-found-copy">
        <p className="not-found-eyebrow">404 · PAGE NOT FOUND</p>
        <h1 id="not-found-title">A little off course.</h1>
        <p className="not-found-description">
          This page may have moved, or the link isn’t quite right.
          <br className="not-found-break" /> Let’s get you somewhere familiar.
        </p>
        <div className="not-found-actions">
          <Link className="button-primary" to={signedOut ? '/sign-in' : '/'}>
            <LayoutDashboard size={17} aria-hidden="true" />
            {signedOut ? 'Go to sign in' : 'Back to Overview'}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
          {!signedOut && (
            <Link className="not-found-documents" to="/documents">
              <Files size={17} aria-hidden="true" /> Browse documents
              <ArrowUpRight size={15} aria-hidden="true" />
            </Link>
          )}
        </div>
        <p className="not-found-footnote">
          Just a missing page. Your saved reviews are still in your workspace.
        </p>
      </div>
    </section>
  )

  return signedOut ? (
    <div className="not-found-public">
      <header>
        <Link to="/welcome" aria-label="OpenAnonymi home">
          <Brand />
        </Link>
      </header>
      <main id="main-content">{content}</main>
    </div>
  ) : (
    content
  )
}
