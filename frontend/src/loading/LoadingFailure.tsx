import { EntranceFrame } from './EntranceFrame'
import './loading.css'

export function LoadingFailure({ title, message, onRetry, fullScreen = false, protectEdits = false }: {
  title: string; message: string; onRetry: () => void; fullScreen?: boolean; protectEdits?: boolean
}) {
  const notice = <section className="loading-state loading-failure" role="alert">
    <svg className="loading-failure-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M13 8h15l8 8v24H12V8h1Zm15 0v8h8M19 23h10M19 29h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="35" cy="35" r="8" fill="var(--surface)" stroke="currentColor" strokeWidth="1.5" />
      <path d="M35 31v4m0 3v.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
    <h2>{title}</h2>
    <p>{message}</p>
    {protectEdits && <p>Copy any unprotected edits before reloading this page.</p>}
    <button type="button" onClick={onRetry}>{protectEdits ? 'Reload this page' : 'Try again'}</button>
  </section>
  return fullScreen ? <EntranceFrame eyebrow="Let’s get you back">{notice}</EntranceFrame> : notice
}
