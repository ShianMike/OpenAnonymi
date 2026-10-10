import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { IntakeSource } from './IntakeSource'
import type { IntakeController } from './useIntake'

const intake = {
  pending: false, title: '', workspaceId: 'local', mode: 'file', file: null,
  fileNotes: [], filePagePreviews: [], filePages: null, hasFilePreview: false,
  characters: 0, overLimit: false, fileEdited: false, fileText: '',
  csvDelimiter: 'auto', csvHeader: 'auto',
} as unknown as IntakeController

it('shows formats before upload and a compact, editable comparison after reading a scan', () => {
  const empty = renderToStaticMarkup(<IntakeSource intake={intake} />)
  expect(empty).toContain('Drop your document here')
  expect(empty).toContain('Supported files and size limits')
  const loaded = renderToStaticMarkup(<IntakeSource intake={{ ...intake,
    file: new File(['fictional scan'], 'scan.pdf'), filePages: 2, hasFilePreview: true,
    fileText: 'Corrected text from both pages', characters: 30,
    fileNotes: ['Check reading order'],
    filePagePreviews: [{ page_number: 1, data_url: 'data:image/jpeg;base64,scan' }],
  }} />)
  expect(loaded).toContain('intake-dropzone has-file')
  expect(loaded).toContain('2 pages')
  expect(loaded).toContain('Change file')
  expect(loaded).not.toContain('Supported files and size limits')
  expect(loaded).toContain('All pages · editable')
  expect(loaded).toContain('Corrected text from both pages')
  expect(loaded).toContain('File notes &amp; tips')
  expect(loaded).toContain('Check reading order')
  expect(loaded).toContain('File and scan limits')
})

it('retains CSV format controls and the warning about resetting corrections', () => {
  const html = renderToStaticMarkup(<IntakeSource intake={{ ...intake,
    file: new File(['name,email\nNora,nora@example.test'], 'contacts.csv'),
    hasFilePreview: true, fileText: 'name,email\nNora,nora@example.test',
  }} />)
  expect(html).toContain('How are columns separated?')
  expect(html).toContain('Detect column names')
  expect(html).toContain('Changing how columns are read resets this text.')
  expect(html).not.toContain('Original scan')
})
