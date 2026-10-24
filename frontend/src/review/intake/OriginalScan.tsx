import { useState } from 'react'
import { ChevronLeft, ChevronRight, Minimize, ZoomIn } from 'lucide-react'
import type { ImportPreview } from '../../imports/api'
import { cn } from '../../ui/cn'
import './original-scan.css'

export function OriginalScan({ pages, totalPages, pdf = false }: {
  pages: NonNullable<ImportPreview['page_previews']>; totalPages: number | null; pdf?: boolean
}) {
  const [index, setIndex] = useState(0)
  const [zoomed, setZoomed] = useState(false)
  const visibleIndex = Math.min(index, pages.length - 1)
  const page = pages[visibleIndex]
  if (!page) return null
  return <figure className="intake-original-scan">
    <figcaption>
      <strong>{pdf ? 'Original PDF layout' : 'Original scan'}</strong>
      <button type="button" className="quiet-button" aria-pressed={zoomed}
        onClick={() => setZoomed(!zoomed)}>{zoomed ? <Minimize size={15} aria-hidden="true" /> : <ZoomIn size={15} aria-hidden="true" />}{zoomed ? 'Fit page' : 'Zoom in'}</button>
    </figcaption>
    <div key={page.page_number} className={cn('intake-scan-image', zoomed && 'is-zoomed')}
      tabIndex={0} role="region" aria-label={pdf ? 'Original PDF preview' : 'Original scan preview'}>
      <img src={page.data_url} alt={`Original ${pdf ? 'PDF' : 'scanned'} page ${page.page_number}`} />
    </div>
    <div className="intake-scan-pages">
      <button type="button" className="quiet-icon" aria-label={pdf ? 'Previous PDF page' : 'Previous scanned page'} disabled={visibleIndex === 0}
        onClick={() => setIndex(visibleIndex - 1)}><ChevronLeft size={17} aria-hidden="true" /></button>
      <span role="status" aria-live="polite" aria-atomic="true">Page {page.page_number}{totalPages ? ` of ${totalPages}` : ''}</span>
      <button type="button" className="quiet-icon" aria-label={pdf ? 'Next PDF page' : 'Next scanned page'} disabled={visibleIndex === pages.length - 1}
        onClick={() => setIndex(visibleIndex + 1)}><ChevronRight size={17} aria-hidden="true" /></button>
    </div>
    <p className="field-note">{pdf ? 'Page appearance is retained for review and PDF export.' : 'Scanned pages only. The original file is not saved.'}</p>
  </figure>
}
