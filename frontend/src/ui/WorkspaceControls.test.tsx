import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { InlineNotice } from './WorkspaceControls'

it('gives actionable errors an accessible title and a separate recovery area', () => {
  const html = renderToStaticMarkup(<InlineNotice error title="Workspace access unavailable" actions={<button type="button">Check access again</button>}>Administrator access is required.</InlineNotice>)
  expect(html).toMatch(/role="alert" aria-labelledby="[^"]+"/)
  expect(html).toContain('Workspace access unavailable</strong>')
  expect(html).toContain('Administrator access is required.</div><div class="inline-notice-actions"><button type="button">Check access again</button>')
  expect(html).not.toContain('role="status"')
})

it('keeps simple notices concise and announces them without an error alert', () => {
  const html = renderToStaticMarkup(<InlineNotice>Preferences saved.</InlineNotice>)
  expect(html).toContain('role="status"')
  expect(html).toContain('Preferences saved.')
  expect(html).not.toContain('aria-labelledby')
  expect(html).not.toContain('inline-notice-actions')
  expect(html).not.toContain('inline-notice-title')
})
