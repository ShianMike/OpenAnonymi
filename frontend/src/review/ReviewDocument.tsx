import { useEffect } from 'react'
import { FileText, Eye, ListFilter, Undo2 } from 'lucide-react'
import * as Tabs from '@radix-ui/react-tabs'
import type { ReviewController } from './useReviewController'
import { ReviewSource } from './ReviewSource'
import { ReviewPreview } from './ReviewPreview'
import { KeyboardReview } from '../keyboard/KeyboardReview'

export function ReviewDocument({ review, userId }: { review: ReviewController; userId: string }) {
  const { mobilePanel, setMobilePanel } = review
  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 761px)')
    const sync = () => { if (desktop.matches && mobilePanel === 'findings') setMobilePanel('original') }
    sync(); desktop.addEventListener('change', sync)
    return () => desktop.removeEventListener('change', sync)
  }, [mobilePanel, setMobilePanel])
  return <div className="studio-document-area">
    <div className="studio-document-toolbar">
      <Tabs.Root value={review.mobilePanel} onValueChange={panel => review.setMobilePanel(panel as typeof review.mobilePanel)}>
        <Tabs.List className="studio-view-switch" aria-label="Document view">
          {([['original', 'Document', FileText], ['preview', 'Output', Eye], ['findings', 'Findings', ListFilter]] as const).map(([panel, label, Icon]) =>
            <Tabs.Trigger key={panel} value={panel} id={`review-${panel}-tab`} aria-controls={`review-${panel}-panel`} className={panel === 'findings' ? 'studio-mobile-findings' : undefined}>
              <Icon size={15} /><span>{label}</span>{panel === 'findings' && <small>{review.activeFindings.length}</small>}
            </Tabs.Trigger>)}
        </Tabs.List>
      </Tabs.Root>
      <div className="studio-document-tools"><button className="studio-icon" type="button" aria-label="Undo last review edit" disabled={!review.undoCount || review.dirty || review.settingsDirty || review.actionPending || review.conflict} onClick={() => void review.undoReview()}><Undo2 size={16} /></button>
        <KeyboardReview key={`${userId}.${review.documentId}`} review={review} userId={userId} compact /></div>
    </div>
    <div className="studio-canvas">
      <div className="studio-paper" data-file-format={review.state.kind === 'ready' ? review.state.saved.file_format : undefined}><ReviewSource review={review} /><ReviewPreview review={review} /></div>
    </div>
  </div>
}
