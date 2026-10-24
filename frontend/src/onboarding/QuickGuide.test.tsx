import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { DecisionExample, QuickGuideButton, QuickGuideProvider, QuickGuideSteps } from './QuickGuide'
import { hasSeenGuide, rememberGuide } from './guideSeen'

let values: Map<string, string>
beforeEach(() => {
  values = new Map()
  vi.stubGlobal('window', { localStorage: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  } })
})
afterEach(() => vi.unstubAllGlobals())

const render = (path = '/documents', userId = 'first-user', offer = true) => renderToStaticMarkup(
  <MemoryRouter initialEntries={[path]}><QuickGuideProvider userId={userId} offer={offer}>
    <QuickGuideButton />
  </QuickGuideProvider></MemoryRouter>,
)

it('offers a skippable introduction on first use and always leaves a replay button', () => {
  const first = render()
  expect(first).toContain('Your first review, step by step.')
  expect(first).toContain('Show me around')
  expect(first).toContain('Not now')
  expect(first).toContain('Dismiss quick guide introduction')
  expect(first).not.toContain('role="dialog"')
  expect(first).not.toContain('autofocus')
  expect(first).not.toContain('<form')
  expect(hasSeenGuide('first-user')).toBe(false)
  rememberGuide('first-user')
  const returning = render()
  expect(returning).not.toContain('guide-welcome-title')
  expect(returning).toContain('<span>Quick guide</span>')
  expect(values.size).toBe(1)
  expect([...values.values()]).toEqual(['seen'])
})

it('scopes dismissal to the signed-in account without storing review content', () => {
  rememberGuide('first-user')
  expect(hasSeenGuide('first-user')).toBe(true)
  expect(hasSeenGuide('second-user')).toBe(false)
  expect(render('/new', 'second-user')).toContain('guide-welcome-title')
  expect([...values.keys()]).toEqual(['openanonymi.quick-guide.first-user'])
})

it('does not interrupt an existing review, security setup, settings or a public page', () => {
  for (const path of ['/documents/review-id/edit', '/settings?section=security', '/welcome', '/rules', '/not-found']) {
    expect(render(path)).not.toContain('guide-welcome-title')
    expect(render(path)).toContain('<span>Quick guide</span>')
  }
  expect(render('/new', 'first-user', false)).not.toContain('guide-welcome-title')
  expect(render('/')).toContain('guide-welcome-title')
  expect(render('/new')).toContain('guide-welcome-in-editor')
})

it('still works when browser storage is unavailable or contains an unknown value', () => {
  values.set('openanonymi.quick-guide.first-user', 'unexpected')
  expect(hasSeenGuide('first-user')).toBe(false)
  vi.stubGlobal('window', { get localStorage() { throw new Error('Storage blocked') } })
  expect(() => rememberGuide('first-user')).not.toThrow()
  expect(hasSeenGuide('first-user')).toBe(false)
  expect(render()).toContain('Show me around')
})

it.each([
  ['replace', 'EMAIL_001', 'A category label replaces this email address.'],
  ['hide', '[REDACTED]', 'The detail is covered with a redaction marker.'],
  ['keep', 'alex@example.test', 'Keep requires a reason.'],
] as const)('explains the visible consequence of choosing %s in the fictional practice', (decision, output, explanation) => {
  const html = renderToStaticMarkup(<DecisionExample decision={decision} onChange={() => {}} />)
  expect(html).toContain(`aria-pressed="true">${decision === 'replace' ? 'Replace' : decision === 'hide' ? 'Hide' : 'Keep'}</button>`)
  expect(html).toContain(`<strong>${output}</strong>`)
  expect(html).toContain(explanation)
  expect(html).toContain('role="status" aria-live="polite" aria-atomic="true"')
  expect(html).toContain('Practice only')
})

it('provides four keyboard-navigable topics with the actual workflow and a finite end', () => {
  const first = renderToStaticMarkup(<QuickGuideSteps onDone={() => {}} />)
  expect(first.match(/role="tab"/g)).toHaveLength(4)
  expect(first).toContain('aria-label="Quick guide steps"')
  expect(first).toContain('Save as draft')
  expect(first).not.toContain('Excel')
  expect(first).toContain('disabled=""')
  const decisions = renderToStaticMarkup(<QuickGuideSteps initialTopic="decisions" onDone={() => {}} />)
  expect(decisions).toContain('Choose an action to see what changes.')
  expect(decisions).toContain('Mark text')
  const last = renderToStaticMarkup(<QuickGuideSteps initialTopic="export" onDone={() => {}} />)
  expect(last).toContain('Prepare download')
  expect(last).toContain('Copy reviewed text')
  expect(last).toContain('Only the document owner can export')
  expect(last).toContain('Got it')
})
