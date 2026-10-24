import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import { useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Users } from 'lucide-react'
import type { SessionView } from '../api/client'
import type { ReviewController } from '../review/useReviewController'
import { StudioDialog } from '../review/studio/StudioControls'
import { HandoffPanel } from './HandoffPanel'
import { FindingDiscussion, type CommentDraft } from './FindingDiscussion'
import { readReviewedOutput } from './reviewerNavigation'
import './team.css'

export function ReviewCollaboration({ review, session }: { review: ReviewController; session: SessionView }) {
  const location = useLocation()
  const panel = new URLSearchParams(location.search).get('panel')
  const [open, setOpen] = useState(panel === 'discussion' || panel === 'reviewer')
  const [view, setView] = useState(panel === 'discussion' ? 'discussion' : 'reviewer')
  const [busy, setBusy] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, CommentDraft>>({})
  const [finding, setFinding] = useState(review.selectedFindingId ?? review.activeFindings[0]?.finding_id ?? '')
  const readingOutput = useRef(false)
  if (review.state.kind !== 'ready') return null
  const saved = review.state.saved
  const hasDraft = Object.values(drafts).some(draft => draft.text.trim())
  function changeDraft(finding: string, text: string) {
    setDrafts(current => {
      const next = { ...current }
      if (text) next[finding] = { text, id: crypto.randomUUID() }; else delete next[finding]
      return next
    })
  }
  return <Dialog.Root open={open} onOpenChange={next => {
    if (busy) return
    if (next && !review.activeFindings.some(item => item.finding_id === finding)) setFinding(review.selectedFindingId ?? review.activeFindings[0]?.finding_id ?? '')
    setOpen(next)
  }}>
    <Dialog.Trigger asChild><button type="button" className="studio-button studio-team-trigger" id="review-collaboration-trigger" aria-label="Collaborate"><Users size={16} aria-hidden="true" /><span>Collaborate</span></button></Dialog.Trigger>
    <StudioDialog title="Review together" description="Manage review access and discuss individual findings." className="collaboration-dialog" busy={busy}
      onCloseAutoFocus={event => {
        if (readingOutput.current) { event.preventDefault(); readingOutput.current = false; readReviewedOutput(review) }
      }}>
      <Tabs.Root value={view} onValueChange={setView} className="collaboration-views">
        <Tabs.List className="collaboration-tabs" aria-label="Collaboration views">
          <Tabs.Trigger value="reviewer" disabled={busy}>{saved.can_edit ? 'Reviewer' : 'Your review'}</Tabs.Trigger>
          <Tabs.Trigger value="discussion" disabled={busy}>Discussion{hasDraft && <span className="collaboration-draft-badge">Draft</span>}</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="reviewer" forceMount className="collaboration-tab">
          <HandoffPanel key={`${saved.version.source_revision_id}.${saved.version.decision_version}.${saved.status}`} review={review} session={session} busy={busy} onBusyChange={setBusy}
            onSaved={() => setOpen(false)} onReadOutput={() => { readingOutput.current = true; setOpen(false) }} />
        </Tabs.Content>
        <Tabs.Content value="discussion" forceMount className="collaboration-tab">
          <FindingDiscussion key={saved.version.source_revision_id} review={review} session={session} active={view === 'discussion'} busy={busy} onBusyChange={setBusy} finding={finding} onFindingChange={setFinding} drafts={drafts} onDraftChange={changeDraft} />
        </Tabs.Content>
      </Tabs.Root>
    </StudioDialog>
  </Dialog.Root>
}
