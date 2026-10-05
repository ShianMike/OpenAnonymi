import { describe, expect, it } from 'vitest'
import { segmentText, type ReviewFinding } from './textSegments'

function finding(id: string, start: number, end: number): ReviewFinding {
  return {
    finding_id: id,
    span: { start, end },
    category: 'person',
    origin: 'manual',
    action: null,
    style: 'token',
    style_option: null,
    date_format: null,
    group_id: null,
    label: null,
    keep_reason: null,
    reason: null,
    rule_id: null,
    rule_version: null,
  }
}

describe('inline review text', () => {
  it('preserves Unicode, combining characters and line endings while marking API code point ranges', () => {
    const text = '😀 Zoë\r\n東京 e\u0301'
    const person = finding('person', 2, 5)
    const place = finding('place', 7, 9)
    const result = segmentText(
      text,
      [person, place].map((item) => ({ span: item.span, finding: item })),
    )
    expect(result.map((part) => part.text).join('')).toBe(text)
    expect(result.filter((part) => part.findings.length).map((part) => part.text)).toEqual([
      'Zoë',
      '東京',
    ])
  })

  it('preserves every character and both finding identities in overlapping ranges', () => {
    const first = finding('first', 1, 5)
    const second = finding('second', 3, 7)
    const result = segmentText(
      'abcdefgh',
      [first, second].map((item) => ({ span: item.span, finding: item })),
    )
    expect(result.map((part) => part.text).join('')).toBe('abcdefgh')
    expect(
      result.find((part) => part.text === 'de')?.findings.map((item) => item.finding_id),
    ).toEqual(['first', 'second'])
  })

  it('preserves adjacent marks, ignores invalid ranges, and leaves text with no findings intact', () => {
    const valid = [finding('first', 0, 2), finding('second', 2, 4)]
    const invalid = [finding('negative', -1, 3), finding('outside', 2, 9), finding('empty', 1, 1)]
    const result = segmentText(
      'abcd',
      [...valid, ...invalid].map((item) => ({ span: item.span, finding: item })),
    )
    expect(result.map((part) => part.text)).toEqual(['ab', 'cd'])
    expect(result.map((part) => part.findings[0].finding_id)).toEqual(['first', 'second'])
    expect(segmentText('untouched', [])[0].text).toBe('untouched')
    expect(segmentText('', [])).toEqual([])
  })

  it('keeps input precedence for unsorted nested spans and removes ended marks at a shared boundary', () => {
    const marks = [finding('inner', 3, 5), finding('outer', 0, 8), finding('next', 5, 7)]
    const result = segmentText('abcdefgh', marks.map(item => ({ span: item.span, finding: item })))
    expect(result.map(part => [part.text, part.findings.map(item => item.finding_id)])).toEqual([
      ['abc', ['outer']], ['de', ['inner', 'outer']], ['fg', ['outer', 'next']], ['h', ['outer']],
    ])
  })
})
