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
  const starts = new Map<number, number[]>()
  const ends = new Map<number, number[]>()
  valid.forEach(({ span }, index) => {
    starts.set(span.start, [...(starts.get(span.start) ?? []), index])
    ends.set(span.end, [...(ends.get(span.end) ?? []), index])
  })
  const active = new Set<number>()
  const segments: TextSegment[] = []
  for (let index = 0; index < boundaries.length - 1; index++) {
    const start = boundaries[index]
    const end = boundaries[index + 1]
    if (start === end) continue
    for (const mark of ends.get(start) ?? []) active.delete(mark)
    for (const mark of starts.get(start) ?? []) active.add(mark)
    segments.push({
      text: characters.slice(start, end).join(''),
      start,
      end,
      // Input order determines which overlapping finding opens from a mark.
      findings: Array.from(active).sort((a, b) => a - b).map(mark => valid[mark].finding),
    })
  }
  return segments
}
