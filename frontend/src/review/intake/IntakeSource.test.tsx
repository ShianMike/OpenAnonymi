import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { IntakeSource } from './IntakeSource'
import type { IntakeController } from './useIntake'

const intake = {
  pending: false, title: '', workspaceId: 'local', mode: 'paste', source: '', file: null,
  fileNotes: [], filePagePreviews: [], filePages: null, hasFilePreview: false,
  characters: 0, overLimit: false, fileEdited: false, fileText: '',
} as unknown as IntakeController

it('starts with one text editor and an optional file input', () => {
  const empty = renderToStaticMarkup(<IntakeSource intake={intake} />)
  expect(empty).toContain('id="source-text"')
  expect(empty).toContain('Write or paste the text you want to review…')
  expect(empty).toContain('aria-label="Add a file to review"')
  expect(empty).toContain('Supported files &amp; limits')
  expect(empty).toContain('You can drop one file anywhere in the editor.')
  expect(empty).not.toContain('source-mode')
  expect(empty).not.toContain('.xlsx')
  expect(empty).not.toContain('Excel')
})

it('keeps pasted text available and preserves PDF source positions after reading a scan', () => {
  const loaded = renderToStaticMarkup(<IntakeSource intake={{ ...intake,
    mode: 'file', source: 'A separate pasted draft',
    file: new File(['fictional scan'], 'scan.pdf'), filePages: 2, hasFilePreview: true,
    fileText: 'Corrected text from both pages', characters: 30,
    fileNotes: ['Check reading order'],
    filePagePreviews: [{ page_number: 1, data_url: 'data:image/jpeg;base64,scan' }],
  }} />)
  expect(loaded).toContain('studio-file-row')
  expect(loaded).toContain('Your pasted text is still here. Remove the file to return to it.')
  expect(loaded).toContain('aria-label="Remove file and return to text"')
  expect(loaded).not.toContain('A separate pasted draft')
  expect(loaded).toContain('2 pages')
  expect(loaded).toContain('14 bytes')
  expect(loaded).toContain('Change file')
  expect(loaded).not.toContain('Supported files &amp; limits')
  expect(loaded).toContain('Read-only · layout preserved')
  expect(loaded).toMatch(/id="file-preview"[^>]*readOnly=""/)
  expect(loaded).toContain('Corrected text from both pages')
  expect(loaded).toContain('File notes &amp; tips')
  expect(loaded).toContain('Check reading order')
  expect(loaded).toContain('Scans support printed English text')
})

it('offers supported document formats without CSV input or column controls', () => {
  const html = renderToStaticMarkup(<IntakeSource intake={intake} />)
  expect(html).not.toContain('.csv')
  expect(html).not.toContain('text/csv')
  expect(html).not.toContain('CSV')
  for (const extension of ['.txt', '.md', '.pdf', '.docx', '.png']) expect(html).toContain(extension)
})

it('keeps file errors and text limits next to the source with an accessible recovery action', () => {
  const failed = renderToStaticMarkup(<IntakeSource intake={{ ...intake, mode: 'file',
    file: new File(['invalid'], 'invalid.zip'), fileError: 'Choose a supported file.' }} />)
  expect(failed).toContain('has-error')
  expect(failed).toContain('role="alert"')
  expect(failed).toContain('Choose a supported file.')
  expect(failed).toContain('aria-label="Remove file and return to text"')
  expect(failed).not.toContain('Text extracted')
  const tooLong = renderToStaticMarkup(<IntakeSource intake={{ ...intake, overLimit: true, characters: 100_001 }} />)
  expect(tooLong).toMatch(/id="source-text"[^>]*aria-invalid="true"/)
  expect(tooLong).toContain('100,001')
  expect(tooLong).toContain('Shorten your text to 100,000 characters or fewer')
})
