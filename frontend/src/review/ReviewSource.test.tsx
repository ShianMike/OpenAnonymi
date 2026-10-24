import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ReviewController } from './useReviewController'
import { ReviewSource } from './ReviewSource'

vi.mock('./layout/FileLayoutView', () => ({ FileLayoutView: () => <div>PDF page canvas</div> }))

function source(format: 'pdf' | 'txt', editingSource = false) {
  return renderToStaticMarkup(<ReviewSource review={{
    state: { kind: 'ready', saved: { file_format: format, text: 'Synthetic source' } },
    text: 'Synthetic source', activeFindings: [], mobilePanel: 'original', editingSource, dirty: false, canEdit: true,
  } as unknown as ReviewController} />)
}

it('groups PDF display choices with marking while keeping the fixed source read-only', () => {
  const html = source('pdf')
  expect(html).toContain('role="group" aria-label="Source display"')
  expect(html).toMatch(/aria-pressed="true">Page layout<\/button>/)
  expect(html).toMatch(/aria-pressed="false">Text view<\/button>/)
  expect(html).toContain('PDF page canvas')
  expect(html.indexOf('Text view')).toBeLessThan(html.indexOf('document-help'))
  expect(html).toContain('use Mark text to add one')
  expect(html).toMatch(/<textarea[^>]*readonly=""/i)
  expect(html).not.toContain('Save new revision')
})

it('keeps PDF marking focused on the read-only text selection', () => {
  const html = source('pdf', true)
  expect(html).toContain('View document')
  expect(html).not.toContain('aria-label="Source display"')
  expect(html).not.toContain('PDF page canvas')
  expect(html).toContain('Select text to mark a detail')
  expect(html).toMatch(/<textarea[^>]*readonly=""/i)
  expect(html).not.toContain('Save new revision')
})

it('retains normal text editing without PDF display controls', () => {
  const html = source('txt')
  expect(html).toContain('Source text')
  expect(html).toContain('Edit text')
  expect(html).toContain('Save new revision')
  expect(html).not.toContain('aria-label="Source display"')
  expect(html).not.toMatch(/<textarea[^>]*readonly=""/i)
})
