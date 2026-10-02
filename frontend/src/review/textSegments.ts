import type { FindingsView, SourceSpan } from '../api/client'

export type ReviewFinding = FindingsView['findings'][number]
export type TextMark = { span: SourceSpan; finding: ReviewFinding }
export type TextSegment = { text: string; start: number; end: number; findings: ReviewFinding[] }

/** Partition by code points, preserving every character even with overlapping findings. */
export function segmentText(text: string, marks: TextMark[]): TextSegment[] {
  const characters = Array.from(text)
  const valid = marks.filter(
    ({ span }) =>
      Number.isInteger(span.start) &&
      Number.isInteger(span.end) &&
      span.start >= 0 &&
      span.end <= characters.length &&
      span.start < span.end,
  )
  const boundaries = Array.from(
    new Set([0, characters.length, ...valid.flatMap(({ span }) => [span.start, span.end])]),
  ).sort((a, b) => a - b)
  const segments: TextSegment[] = []
  for (let index = 0; index < boundaries.length - 1; index++) {
    const start = boundaries[index]
    const end = boundaries[index + 1]
    if (start === end) continue
    segments.push({
      text: characters.slice(start, end).join(''),
      start,
      end,
      findings: valid
        .filter(({ span }) => span.start <= start && span.end >= end)
        .map(({ finding }) => finding),
    })
  }
  return segments
}
