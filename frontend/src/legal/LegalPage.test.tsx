import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { AppCredit } from '../ui/AppCredit'
import { LegalPage } from './LegalPage'

it.each(['terms', 'privacy'] as const)('keeps the %s notice navigable and uses the shared support address', (notice) => {
  const html = renderToStaticMarkup(<MemoryRouter><LegalPage notice={notice} /></MemoryRouter>)
  for (const [, id] of html.matchAll(/href="#([^"]+)"/g)) expect(html).toContain(`id="${id}"`)
  const supportAddress = renderToStaticMarkup(<AppCredit />).match(/href="(mailto:[^"]+)"/)?.[1]
  expect(supportAddress).toBe('mailto:support@openanonymi.com')
  expect(html).toContain(`href="${supportAddress}"`)
  expect(html).toContain('aria-current="page"')
  expect(html).toContain('Shian Meris, based in the Philippines')
  expect(html).not.toContain('<form')
})

it('opens shared legal links separately so pending account and review forms stay open', () => {
  const html = renderToStaticMarkup(<AppCredit />)
  for (const path of ['/terms', '/privacy']) {
    expect(html).toContain(`href="${path}" target="_blank" rel="noopener noreferrer"`)
  }
})
