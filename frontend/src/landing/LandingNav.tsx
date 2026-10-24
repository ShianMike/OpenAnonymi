import { Link } from 'react-router-dom'
import { Brand } from '../ui/Brand'
import { landingSections } from './links'

export function LandingNav({ signedIn, startTo, scrolled }: { signedIn: boolean; startTo: string; scrolled: boolean }) {
  return (
    <header className="landing-nav" data-scrolled={scrolled}>
      <div className="landing-container landing-nav-inner">
        <Link className="landing-brand" to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link>
        <nav className="landing-nav-links" aria-label="Explore OpenAnonymi">
          {landingSections.map(({ href, label }) => <a key={href} href={href}>{label}</a>)}
        </nav>
        <div className="landing-nav-actions">
          <Link className="landing-nav-link" to={signedIn ? '/documents' : '/sign-in'}>{signedIn ? 'Open documents' : 'Sign in'}</Link>
          <Link className="landing-button landing-button-sm landing-nav-start" to={startTo}>Start a review</Link>
        </div>
      </div>
    </header>
  )
}
