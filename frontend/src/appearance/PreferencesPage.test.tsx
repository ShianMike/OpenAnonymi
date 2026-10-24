import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

const state = vi.hoisted(() => ({ appearance: { preference: 'light', theme: 'light', saved: true, setAppearance: () => {} },
  display: { density: 'comfortable', fontSize: 'standard', motion: 'system', saved: true, setDisplayPreference: () => {} } }))
vi.mock('./useAppearance', () => ({ useAppearance: () => state.appearance }))
vi.mock('./useDisplayPreferences', () => ({ useDisplayPreferences: () => state.display }))
import { PreferencesPage } from './PreferencesPage'

it('provides three native theme choices and labelled spacing, size and motion controls inside settings', () => {
  const html = renderToStaticMarkup(<PreferencesPage />)
  expect(html.match(/type="radio"/g)).toHaveLength(3)
  expect(html.match(/<input[^>]*aria-label="Light"[^>]*>/)?.[0]).toContain('checked=""')
  expect(html).toContain('name="appearance"')
  expect(html).toContain('for="display-spacing"')
  expect(html).toContain('for="display-font-size"')
  expect(html).toContain('for="display-motion"')
  expect(html).toContain('Changes apply immediately and are saved on this device')
  expect(html).not.toContain('<h1')
})

it('does not claim preferences were saved when storage is unavailable', () => {
  state.appearance.saved = false
  try {
    const html = renderToStaticMarkup(<PreferencesPage />)
    expect(html).toContain('Applied for this visit')
    expect(html).toContain('Your browser is not allowing saved preferences')
    expect(html).not.toContain('Changes apply immediately and are saved on this device')
  } finally { state.appearance.saved = true }
})
