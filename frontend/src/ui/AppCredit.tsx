import './app-credit.css'

const source = 'https://github.com/ShianMike/OpenAnonymi'

export function AppCredit() {
  return <small className="app-credit">
    <a href={source}>Powered by OpenAnonymi</a>
    <span>© 2026 ShianMike · <a href={`${source}/blob/main/NOTICE`}>License & notices</a></span>
    <span className="app-credit-links"><a href="/terms" target="_blank" rel="noopener noreferrer" aria-label="Terms of Service (opens in a new tab)">Terms</a><a href="/privacy" target="_blank" rel="noopener noreferrer" aria-label="Privacy Notice (opens in a new tab)">Privacy</a><a href="mailto:support@openanonymi.com">Support</a></span>
  </small>
}
