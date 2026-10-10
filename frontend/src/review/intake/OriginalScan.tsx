import { useState } from 'react'
import { ChevronLeft, ChevronRight, ZoomIn } from 'lucide-react'
import type { ImportPreview } from '../../imports/api'
import { cn } from '../../ui/cn'

export function OriginalScan({ pages, totalPages }: {
  pages: NonNullable<ImportPreview['page_previews']>; totalPages: number | null
}) {
  const [index, setIndex] = useState(0)
  const [zoomed, setZoomed] = useState(false)
  const page = pages[index]
  if (!page) return null
  return <figure className="intake-original-scan">
    <figcaption>
      <strong>Original scan</strong>
      <button type="button" className="quiet-button" aria-pressed={zoomed}
        onClick={() => setZoomed(!zoomed)}><ZoomIn size={15} aria-hidden="true" />{zoomed ? 'Fit page' : 'Zoom'}</button>
    </figcaption>
    <div key={page.page_number} className={cn('intake-scan-image', zoomed && 'is-zoomed')}
      tabIndex={0} role="region" aria-label="Original scan preview">
      <img src={page.data_url} alt={`Original scanned page ${page.page_number}`} />
    </div>
    <div className="intake-scan-pages">
      <button type="button" className="quiet-icon" aria-label="Previous scanned page" disabled={index === 0}
        onClick={() => setIndex(index - 1)}><ChevronLeft size={17} aria-hidden="true" /></button>
      <span role="status">Page {page.page_number}{totalPages ? ` of ${totalPages}` : ''}</span>
      <button type="button" className="quiet-icon" aria-label="Next scanned page" disabled={index === pages.length - 1}
        onClick={() => setIndex(index + 1)}><ChevronRight size={17} aria-hidden="true" /></button>
    </div>
    <p className="field-note">Scanned pages only. The original file is not saved.</p>
  </figure>
}
