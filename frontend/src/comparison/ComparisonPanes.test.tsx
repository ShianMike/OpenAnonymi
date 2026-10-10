import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ComparisonPanes } from './ComparisonPanes'
import type { ComparisonView } from './api'

it('preserves escaped source text and disables change navigation when revisions are identical', () => {
  const value: ComparisonView = {
    document_id: 'example', before: { id: 'one', number: 1, created_at: '2026-10-08T00:00:00Z' },
    after: { id: 'two', number: 2, created_at: '2026-10-10T00:00:00Z' },
    changes: 1, added_lines: 1, removed_lines: 1, coarse: false,
    blocks: [{ kind: 'replace', change: 1, left_start: 1, right_start: 1, left_lines: 1, right_lines: 1,
      left_text: '<original@example.test>', right_text: '<updated@example.test>' }],
  }
  const html = renderToStaticMarkup(<ComparisonPanes value={value} />)
  expect(html).toContain('&lt;original@example.test&gt;')
  expect(html).toContain('&lt;updated@example.test&gt;')
  expect(html).not.toContain('<updated@example.test>')
  expect(html).toContain('Change 1: replace')
  const identical = renderToStaticMarkup(<ComparisonPanes value={{ ...value, changes: 0, added_lines: 0, removed_lines: 0,
    blocks: [{ ...value.blocks[0], kind: 'equal', change: null, right_text: value.blocks[0].left_text }] }} />)
  expect(identical).toContain('No source changes')
  const navigation = identical.match(/<button\b[^>]*>/g)!.filter(button => button.includes('change'))
  expect(navigation).toHaveLength(2)
  expect(navigation.every(button => button.includes('disabled=""'))).toBe(true)
})
