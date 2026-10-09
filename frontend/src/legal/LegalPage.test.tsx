import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { AppCredit } from '../ui/AppCredit'
import { LegalPage } from './LegalPage'

it.each(['terms', 'privacy'] as const)('keeps the %s notice navigable and uses the shared support address', (notice) => {
  const html = renderToStaticMarkup(<MemoryRouter><LegalPage notice={notice} /></MemoryRouter>)
  for (const [, id] of html.matchAll(/href="#([^"]+)"/g)) expect(html).toContain(`id="${id}"`)
  const supportAddress = 'mailto:support@openanonymi.com'
  expect(html).toContain(`href="${supportAddress}"`)
  expect(html).toContain('aria-current="page"')
  expect(html).toContain('Shian Meris, based in the Philippines')
  expect(html).not.toContain('<form')
})

it('groups the shared footer actions while preserving the attribution', () => {
  const html = renderToStaticMarkup(<AppCredit />)
  expect(html).toContain('Powered by OpenAnonymi')
  expect(html).toContain('© 2026 ShianMike')
  expect(html).toContain('Legal &amp; support')
  expect(html).toContain('aria-haspopup="menu"')
})
