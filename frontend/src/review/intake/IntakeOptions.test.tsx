import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { IntakeOptions } from './IntakeOptions'
import { OriginalScan } from './OriginalScan'
import type { IntakeController } from './useIntake'
import { detectionChoices } from '../../detection/categories'

const intake = { defaults: { kind: 'ready', value: { content_retention_days: 7, current_time: '2026-10-22T00:00:00Z' }, presets: [] },
  pending: false, emailEnabled: true, phoneEnabled: true, extraCategories: [], presetId: '', phoneRegion: 'PH', retentionDays: 7,
} as unknown as IntakeController
const render = (value = intake) => renderToStaticMarkup(<IntakeOptions intake={value} />)

it('keeps coverage, custom categories and retention in one editable setup', () => {
  const html = render()
  for (const label of ['Contact details', 'People &amp; places', 'Full review', 'Philippines', '7 days']) expect(html).toContain(label)
  expect(html).toContain('2 of 11 selected')
  expect(html).toMatch(/type="radio" name="scan-coverage"[^>]*checked=""[^>]*value="builtin-contact"/)
  for (const choice of detectionChoices) expect(html).toContain(`id="intake-${choice.category}"`)
  expect(html).toContain('aria-describedby="intake-retention-help"')
  expect(html).toContain('id="intake-preset"')
  expect(html).toContain('All review presets')
  expect(render({ ...intake, presetId: 'builtin-technical' })).toContain('Technical logs')
  expect(html.match(/type="radio" name="scan-coverage"/g)).toHaveLength(3)
  expect(render({ ...intake, emailEnabled: false, phoneEnabled: false })).toContain('No automatic checks. You can mark details yourself.')
  expect(render({ ...intake, pending: true })).toMatch(/id="intake-email"[^>]*disabled/)
})

it('preserves the workspace preset region lock and exposes load failures', () => {
  const configured = { ...intake, presetId: 'saved-preset', phoneRegion: 'US', defaults: { kind: 'ready', value: { content_retention_days: 7, current_time: '2026-10-22T00:00:00Z' },
    presets: [{ id: 'saved-preset', name: 'Team contacts', categories: ['email','phone'], phone_region: 'US', preferred_action: 'label', is_default: true }] } } as unknown as IntakeController
  const html = render(configured)
  expect(html).toContain('Team contacts')
  expect(html).toContain('Set by your workspace preset.')
  expect(html).toMatch(/<button[^>]*disabled=""[^>]*id="phone-region"/)
  expect(render({ ...intake, defaults: { kind: 'error', message: 'Settings unavailable' } })).toContain('Retry settings')
  expect(render({ ...intake, defaults: { kind: 'loading' } })).toContain('role="status"')
})

it('retains original scanned page navigation and extraction disclosure', () => {
  const html = renderToStaticMarkup(<OriginalScan totalPages={3} pages={[
    { page_number: 1, data_url: 'data:image/jpeg;base64,first' }, { page_number: 3, data_url: 'data:image/jpeg;base64,last' },
  ]} />)
  expect(html).toContain('alt="Original scanned page 1"')
  expect(html).toContain('Page 1 of 3')
  expect(html).toContain('aria-label="Previous scanned page" disabled=""')
  expect(html).not.toContain('aria-label="Next scanned page" disabled=""')
  expect(html).toContain('The original file is not saved.')
})

it('shows a bounded, labelled PDF preview and disables both navigation limits for a single page', () => {
  const html = renderToStaticMarkup(<OriginalScan pdf totalPages={1} pages={[{ page_number: 1, data_url: 'data:image/jpeg;base64,page' }]} />)
  expect(html).toContain('aria-label="Original PDF preview"')
  expect(html).toContain('alt="Original PDF page 1"')
  expect(html).toContain('aria-label="Previous PDF page" disabled=""')
  expect(html).toContain('aria-label="Next PDF page" disabled=""')
  expect(html).toContain('aria-pressed="false"')
  expect(html).toContain('Page appearance is retained for review and PDF export.')
  expect(renderToStaticMarkup(<OriginalScan totalPages={0} pages={[]} />)).toBe('')
})
