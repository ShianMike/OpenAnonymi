import { describe, expect, it } from 'vitest'
import {
  codePointOffsetToUtf16,
  codePointRangeToUtf16,
  utf16OffsetToCodePoint,
} from './offsets'

describe('source offsets at the JavaScript boundary', () => {
  it('keeps emoji, non-English text, combining characters, and line endings aligned', () => {
    const source = 'A😀ée\u0301\r\n東京'
    expect([...source]).toHaveLength(9)
    expect(codePointOffsetToUtf16(source, 2)).toBe(3)
    expect(utf16OffsetToCodePoint(source, 3)).toBe(2)
    expect(codePointRangeToUtf16(source, 6, 9)).toEqual({ start: 7, end: 10 })
    const range = codePointRangeToUtf16(source, 7, 9)
    expect(source.slice(range.start, range.end)).toBe('東京')
  })

  it('rejects offsets inside an emoji or outside the text', () => {
    expect(() => utf16OffsetToCodePoint('A😀B', 2)).toThrow(RangeError)
    expect(() => codePointOffsetToUtf16('A😀B', 4)).toThrow(RangeError)
    expect(() => codePointRangeToUtf16('abc', 2, 2)).toThrow(RangeError)
  })
})
