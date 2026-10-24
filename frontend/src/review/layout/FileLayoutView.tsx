import { useEffect, useState, useMemo } from 'react'
import { ChevronLeft, ChevronRight, Layers, ZoomIn, ZoomOut } from 'lucide-react'
import { getFileLayout, type FileLayoutView as LayoutResponse } from '../../api/client'
import { sameVersion } from '../reviewState'
import type { ReviewController } from '../useReviewController'
import { LoadingState } from '../../loading/LoadingState'
import './file-layout.css'

function chooseFinding(review: ReviewController, id: string) {
  review.setSelectedFindingId(id)
  if (window.matchMedia('(max-width: 760px)').matches) review.setMobilePanel('findings')
  requestAnimationFrame(() => document.getElementById(`finding-${id}`)?.scrollIntoView({ block: 'nearest' }))
}

export function FileLayoutView({ review, variant }: { review: ReviewController; variant: 'original' | 'preview' }) {
  const [result, setResult] = useState<{ key: string; value?: LayoutResponse; error?: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pageIndex, setPageIndex] = useState(0)
  const [zoom, setZoom] = useState(100)
  const savedVersion = review.state.kind === 'ready' ? review.state.saved.version : null
  const documentId = savedVersion?.document_id
  const revisionId = savedVersion?.source_revision_id
  const decisionVersion = savedVersion?.decision_version
  const settingsVersion = savedVersion?.settings_version
  const version = useMemo(() => documentId && revisionId && decisionVersion !== undefined && settingsVersion !== undefined ? { document_id: documentId, source_revision_id: revisionId, decision_version: decisionVersion, settings_version: settingsVersion } : null, [documentId, revisionId, decisionVersion, settingsVersion])
  const key = version ? `${version.document_id}:${version.source_revision_id}:${version.decision_version}:${version.settings_version}:${variant}` : ''
  useEffect(() => {
    if (!version) return
    const controller = new AbortController()
    getFileLayout(version.document_id, variant, controller.signal).then(value => {
      if (controller.signal.aborted) return
      setResult(sameVersion(value.version, version) ? { key, value } : { key, error: 'This review changed. Reload the layout.' })
    }).catch(error => { if (!controller.signal.aborted) setResult({ key, error: error instanceof Error ? error.message : 'Layout could not load.' }) })
    return () => controller.abort()
  }, [key, attempt, version, variant])
  const layout = result?.key === key ? result.value?.layout : null
  if (result?.key === key && result.error) return <div className="file-layout-message" role="alert"><p>{result.error}</p><button type="button" onClick={() => setAttempt(attempt+1)}>Retry layout</button></div>
  if (!layout) return <LoadingState label="Loading document layout…" shape="page" onRetry={() => setAttempt(value => value + 1)} />
  const pages = layout.pages ?? []
  const findingPage = pages.findIndex(page => page.regions?.some(region => region.finding_id === review.selectedFindingId))
  const visiblePage = findingPage >= 0 ? findingPage : Math.min(pageIndex, pages.length-1)
  const page = pages[visiblePage]
  if (!page) return null
  return <div className="file-pdf-view">
    <div className="file-layout-toolbar">
      <span className="file-layout-caption"><Layers size={15} aria-hidden="true"/>{variant === 'original' ? 'Original page layout' : 'Reviewed page layout'}</span>
      <div className="file-layout-controls">
        <div className="file-layout-pagination" role="group" aria-label="PDF page navigation">
          <button type="button" aria-label="Previous PDF page" disabled={visiblePage === 0} onClick={() => { review.setSelectedFindingId(null); setPageIndex(visiblePage-1) }}><ChevronLeft size={15} aria-hidden="true"/></button>
          <span aria-live="polite" aria-atomic="true">{visiblePage+1} / {pages.length}</span>
          <button type="button" aria-label="Next PDF page" disabled={visiblePage >= pages.length-1} onClick={() => { review.setSelectedFindingId(null); setPageIndex(visiblePage+1) }}><ChevronRight size={15} aria-hidden="true"/></button>
        </div>
        <div className="file-layout-zoom" role="group" aria-label="PDF zoom">
          <button type="button" aria-label="Zoom out" disabled={zoom <= 75} onClick={() => setZoom(zoom-25)}><ZoomOut size={15} aria-hidden="true"/></button>
          <span aria-live="polite" aria-atomic="true">{zoom}%</span>
          <button type="button" aria-label="Zoom in" disabled={zoom >= 200} onClick={() => setZoom(zoom+25)}><ZoomIn size={15} aria-hidden="true"/></button>
        </div>
      </div>
    </div>
    <div className="file-pdf-scroll" tabIndex={0} role="region" aria-label={`${variant === 'original' ? 'Original' : 'Reviewed'} PDF page ${visiblePage+1}`}>
      <div className="file-pdf-page" style={{ width: `${zoom}%`, aspectRatio: `${page.width}/${page.height}` }}>
        <img src={`data:image/png;base64,${page.image}`} alt={`${variant === 'original' ? 'Original' : 'Reviewed'} PDF page ${visiblePage+1}. Use ${variant === 'original' ? 'Text view' : 'Plain text'} for accessible content.`}/>
        {page.regions?.map((region, index) => {
          const finding = review.activeFindings.find(f => f.finding_id === region.finding_id)
          return <button key={index} type="button" className="file-pdf-mark" data-finding-id={region.finding_id} aria-label={`${finding?.category ?? 'Marked'} detail. ${region.action ?? 'Needs decision'}. Review finding`} data-action={region.action ?? 'pending'} data-selected={review.selectedFindingId === region.finding_id || undefined} style={{ left: `${region.box[0]/page.width*100}%`, top: `${region.box[1]/page.height*100}%`, width: `${region.box[2]/page.width*100}%`, height: `${region.box[3]/page.height*100}%` }} onClick={() => chooseFinding(review, region.finding_id)}/>
        })}
      </div>
    </div>
    {variant === 'preview' && <p className="file-layout-note">This is the flattened page used for PDF export. Hidden details are removed from its pixels; replacements stay in their original positions.</p>}
  </div>
}
