import { ArrowLeft, ArrowRight } from 'lucide-react'
import { pageWindow } from './pagination'
import './list-pagination.css'

export function ListPagination({ page, total, pageSize, label, hasMore = false, pending = false, onPrevious, onNext }: {
  page: number; total: number; pageSize: number; label: string; hasMore?: boolean; pending?: boolean
  onPrevious: () => void; onNext: () => void
}) {
  const range = pageWindow(total, page, pageSize)
  const noun = label.toLocaleLowerCase()
  return <nav className="list-pagination" aria-label={`${label} pages`}>
    <p role="status">{total ? `${label} ${range.start + 1}–${range.end}${hasMore ? '' : ` of ${total}`}` : `0 ${noun}`}</p>
    <div>
      <button type="button" className="quiet-icon" aria-label={`Previous ${noun}`} disabled={pending || range.page === 0} onClick={onPrevious}>
        <ArrowLeft size={16} aria-hidden="true" />
      </button>
      <span>Page {range.page + 1}{!hasMore && ` of ${range.pages}`}</span>
      <button type="button" className="quiet-icon" aria-label={`Next ${noun}`} disabled={pending || (!hasMore && range.end === total)} onClick={onNext}>
        <ArrowRight size={16} aria-hidden="true" />
      </button>
    </div>
  </nav>
}
