import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { LandingPage } from './LandingPage'

vi.mock('./useLandingMotion', () => ({ useLandingMotion: () => ({ root: { current: null }, sentinel: { current: null }, scrolled: false }) }))

it.each([false, true])('keeps the overview first and links to the review explanation, signed in: %s', signedIn => {
  const html = renderToStaticMarkup(<MemoryRouter><LandingPage signedIn={signedIn} onRetry={() => {}} /></MemoryRouter>)
  const hero = html.slice(html.indexOf('class="landing-hero"'), html.indexOf('</section>', html.indexOf('class="landing-hero"')))
  expect(hero).toContain('Share the story.')
  expect(hero).toContain('Keep control.')
  expect(hero).toContain('current OpenAnonymi workspace overview:')
  expect(hero).toContain('overview-desktop-4k.jpg')
  expect(hero).not.toContain('overview-1440.webp')
  expect(hero).toContain(`href="${signedIn ? '/new' : '/sign-up'}"`)
  expect(hero).toContain('href="#how-it-works"')
  expect(hero).not.toContain('Product walkthrough')
  expect(html.indexOf('class="landing-shot"')).toBeLessThan(html.indexOf('id="how-it-works"'))
  expect(html.match(/id="how-it-works"/g)).toHaveLength(1)
  expect(html).not.toContain('Product walkthrough')
  expect(html).not.toContain('See a review, from start to finish.')
  expect(html).not.toContain('landing-demo')
  expect(html).toContain('without searchable text, forms, annotations, or attachments')
  expect(html).toContain('The service processes the content you submit.')
  expect(html).not.toContain('CSV</li>')
  expect(html).not.toContain('CSV export is available')
  expect(html).not.toContain('Workspace → Continue review')
})
