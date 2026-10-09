import './app-credit.css'

const source = 'https://github.com/ShianMike/OpenAnonymi'

export function AppCredit() {
  return <small className="app-credit">
    <a href={source}>Powered by OpenAnonymi</a>
    <span>© 2026 ShianMike · <a href={`${source}/blob/main/NOTICE`}>License & notices</a></span>
  </small>
}
