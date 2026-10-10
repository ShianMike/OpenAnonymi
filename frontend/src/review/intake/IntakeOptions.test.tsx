import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { IntakeOptions } from './IntakeOptions'
import { OriginalScan } from './OriginalScan'
import type { IntakeController } from './useIntake'
import { detectionChoices } from '../../detection/categories'

it('shows quick coverage choices and explicitly names excluded categories', () => {
  const intake = {
    defaults: { kind: 'ready', value: { content_retention_days: 7, current_time: '2026-10-10T00:00:00Z' }, presets: [] },
    pending: false, emailEnabled: true, phoneEnabled: true, extraCategories: [],
    presetId: '', phoneRegion: 'PH', retentionDays: 7,
  } as unknown as IntakeController
  const html = renderToStaticMarkup(<IntakeOptions intake={intake} />)
  expect(html).toContain('Scan coverage')
  for (const preset of ['Contact details', 'People &amp; places', 'Full review']) expect(html).toContain(preset)
  const scope = html.slice(html.indexOf('class="intake-coverage-summary"'), html.indexOf('<details'))
  expect(scope).toContain('Email addresses')
  expect(scope).toContain('Not checked: People')
  expect(scope).toContain('National IDs')
  expect(html).not.toContain('id="intake-preset"')
  expect(html).toContain('Customize categories')
  expect(html).toContain('Philippines · ')
  expect(html).toContain('7 days')
  const full = renderToStaticMarkup(<IntakeOptions intake={{ ...intake, presetId: 'builtin-full',
    extraCategories: detectionChoices.map(choice => choice.category).filter(category => !['email', 'phone'].includes(category)) }} />)
  expect(full).not.toContain('Not checked:')
  expect(full).not.toMatch(/id="intake-email"[^>]*disabled/)
  const pending = renderToStaticMarkup(<IntakeOptions intake={{ ...intake, pending: true }} />)
  expect(pending).toMatch(/id="intake-email"[^>]*disabled/)
})

it('keeps workspace presets available without duplicating the quick coverage choices', () => {
  const intake = {
    defaults: { kind: 'ready', value: { content_retention_days: 7, current_time: '2026-10-10T00:00:00Z' },
      presets: [{ id: 'saved-preset', name: 'Team contacts', categories: ['email', 'phone'],
        phone_region: 'US', preferred_action: 'hide', is_default: true }] },
    pending: false, emailEnabled: true, phoneEnabled: true, extraCategories: [],
    presetId: 'saved-preset', phoneRegion: 'US', retentionDays: 1,
  } as unknown as IntakeController
  const html = renderToStaticMarkup(<IntakeOptions intake={intake} />)
  expect(html).toContain('Workspace preset')
  expect(html).toContain('Team contacts')
  expect(html).not.toContain('· Built-in')
  expect(html).not.toMatch(/id="intake-email"[^>]*disabled/)
  expect(html).toContain('id="phone-region"')
})

it('labels the original page and permits navigation when another scanned page exists', () => {
  const html = renderToStaticMarkup(<OriginalScan totalPages={3} pages={[
    { page_number: 1, data_url: 'data:image/jpeg;base64,first' },
    { page_number: 3, data_url: 'data:image/jpeg;base64,last' },
  ]} />)
  expect(html).toContain('alt="Original scanned page 1"')
  expect(html).toContain('Page 1 of 3')
  expect(html).toContain('aria-label="Previous scanned page" disabled=""')
  expect(html).not.toContain('aria-label="Next scanned page" disabled=""')
  expect(html).toContain('The original file is not saved.')
})
