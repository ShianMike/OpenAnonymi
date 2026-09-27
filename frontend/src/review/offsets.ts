/** Convert a Unicode code point offset from the API into a JavaScript UTF-16 offset. */
export function codePointOffsetToUtf16(source: string, codePointOffset: number): number {
  if (!Number.isInteger(codePointOffset) || codePointOffset < 0) {
    throw new RangeError('Code point offset must be a non-negative integer')
  }
  let codePoints = 0
  let utf16 = 0
  for (const character of source) {
    if (codePoints === codePointOffset) return utf16
    codePoints += 1
    utf16 += character.length
  }
  if (codePoints === codePointOffset) return utf16
  throw new RangeError('Code point offset exceeds source length')
}

/** Convert a DOM UTF-16 offset into an API code point offset. Reject split surrogate pairs. */
export function utf16OffsetToCodePoint(source: string, utf16Offset: number): number {
  if (!Number.isInteger(utf16Offset) || utf16Offset < 0) {
    throw new RangeError('UTF-16 offset must be a non-negative integer')
  }
  let codePoints = 0
  let utf16 = 0
  for (const character of source) {
    if (utf16 === utf16Offset) return codePoints
    utf16 += character.length
    if (utf16 > utf16Offset) {
      throw new RangeError('UTF-16 offset splits a surrogate pair')
    }
    codePoints += 1
  }
  if (utf16 === utf16Offset) return codePoints
  throw new RangeError('UTF-16 offset exceeds source length')
}

export function codePointRangeToUtf16(
  source: string,
  start: number,
  end: number,
): { start: number; end: number } {
  if (end <= start) throw new RangeError('Source range must be non-empty')
  return {
    start: codePointOffsetToUtf16(source, start),
    end: codePointOffsetToUtf16(source, end),
  }
}
