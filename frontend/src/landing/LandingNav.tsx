import { ArrowUpRight, Moon, Sun } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../ui/Brand'
import { useAppearance } from '../appearance/useAppearance'

export function LandingNav({ signedIn }: { signedIn: boolean }) {
  const { theme, saved, setAppearance } = useAppearance()
  return (
    <header className="landing-nav">
      <div className="landing-nav-inner">
        <Link className="landing-brand" to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link>
        <nav className="landing-section-links" aria-label="Explore OpenAnonymi">
          <a href="#how-it-works">The process</a>
          <a href="#try-review">Try it out</a>
          <a href="#questions">A few questions</a>
        </nav>
        <div className="landing-nav-actions">
          <button type="button" className="landing-theme-button" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            onClick={() => setAppearance(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun size={19} aria-hidden="true" /> : <Moon size={19} aria-hidden="true" />}
          </button>
          <Link className="landing-sign-in" to={signedIn ? '/continue' : '/sign-in'}>{signedIn ? 'Continue review' : 'Sign in'}</Link>
          <Link className="landing-button landing-button-small" to={signedIn ? '/new' : '/sign-up'}>
            {signedIn ? 'New review' : 'Get started'} <ArrowUpRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </div>
      {!saved && <p role="status" className="landing-preference-notice">Appearance changed for this visit. This browser couldn’t save the preference.</p>}
    </header>
  )
}
