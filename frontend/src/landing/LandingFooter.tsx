import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../ui/Brand'
import { landingSections, sourceUrl, supportEmail } from './links'

function External({ href, children }: { href: string; children: string }) {
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}<span className="sr-only"> (opens in a new tab)</span>
    <ArrowUpRight size={13} aria-hidden="true" /></a>
}

export function LandingFooter({ signedIn, startTo }: { signedIn: boolean; startTo: string }) {
  return (
    <footer className="landing-footer">
      <div className="landing-container">
        <div className="landing-footer-top">
          <div className="landing-footer-brand">
            <Link to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link>
            <p>Review personal details in text and documents before you share them.</p>
          </div>
          <nav className="landing-footer-links" aria-label="Footer">
            <div>
              <h2>Product</h2>
              <ul>{landingSections.map(({ href, label }) => <li key={href}><a href={href}>{label}</a></li>)}</ul>
            </div>
            <div>
              <h2>Account</h2>
              <ul>
                <li><Link to={startTo}>Start a review</Link></li>
                <li><Link to={signedIn ? '/documents' : '/sign-in'}>{signedIn ? 'Open documents' : 'Sign in'}</Link></li>
              </ul>
            </div>
            <div>
              <h2>Legal and support</h2>
              <ul>
                <li><Link to="/terms">Terms of Service</Link></li>
                <li><Link to="/privacy">Privacy Notice</Link></li>
                <li><a href={`mailto:${supportEmail}`}>Contact support</a></li>
              </ul>
            </div>
            <div>
              <h2>Open source</h2>
              <ul>
                <li><External href={sourceUrl}>Source code</External></li>
                <li><External href={`${sourceUrl}/blob/main/NOTICE`}>License and notices</External></li>
              </ul>
            </div>
          </nav>
        </div>
        <p className="landing-footer-credit">Powered by OpenAnonymi <span>© 2026 ShianMike</span></p>
      </div>
    </footer>
  )
}
