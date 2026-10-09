import type { CsvInfo, SourceSpan, SourceView } from '../api/client'
import type { ReviewFinding } from './textSegments'

/** Locate one cell using ordered rows; never join text across CSV boundaries. */
export function csvCellAt(csv: CsvInfo, span: SourceSpan): { row: number; column: number } | null {
  if (span.start >= span.end) return null
  let low = 0; let high = csv.cells.length - 1
  while (low <= high) {
    const row = Math.floor((low + high) / 2)
    const cells = csv.cells[row]
    if (!cells.length) return null
    if (span.start < cells[0].start) high = row - 1
    else if (span.start > cells[cells.length - 1].end) low = row + 1
    else {
      const column = cells.findIndex((cell) => cell.start <= span.start && span.end <= cell.end)
      return column < 0 ? null : { row, column }
    }
  }
  return null
}

export function columnFindings(csv: CsvInfo, findings: ReviewFinding[], column: number): ReviewFinding[] {
  return findings.filter((finding) => {
    const cell = csvCellAt(csv, finding.span)
    return cell?.column === column && (!csv.has_header || cell.row > 0)
  }).sort((left, right) => left.span.start - right.span.start)
}

export function columnDefault(source: SourceView, finding: ReviewFinding) {
  if (!source.csv || finding.rule_id !== 'csv.column') return null
  const cell = csvCellAt(source.csv, finding.span)
  if (!cell || (source.csv.has_header && cell.row === 0)) return null
  return source.csv.rules.find((rule) => rule.column === cell.column && rule.mode === 'category' &&
    rule.category === finding.category) ?? null
}
