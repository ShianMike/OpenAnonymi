import { useEffect, useState } from 'react'
import { GitCompareArrows } from 'lucide-react'
import type { DocumentHistoryView } from '../api/client'
import { PanelHeading, InlineNotice } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { GlassSelect } from '../ui/GlassSelect'
import { ComparisonPanes } from './ComparisonPanes'
import { compareRevisions, type ComparisonView } from './api'
import './comparison.css'

type Data = { kind: 'idle' | 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; value: ComparisonView }

export function RevisionComparison({ history }: { history: DocumentHistoryView }) {
  const [before, setBefore] = useState(history.revisions[1]?.id ?? '')
  const [after, setAfter] = useState(history.revisions[0]?.id ?? '')
  const [request, setRequest] = useState<{ before: string; after: string; attempt: number } | null>(null)
  const [data, setData] = useState<Data>({ kind: 'idle' })
  useEffect(() => {
    if (!request) return
    const controller = new AbortController()
    compareRevisions(history.document_id, request.before, request.after, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setData({ kind: 'ready', value }) })
      .catch((cause) => { if (!controller.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'Comparison could not be loaded.' }) })
    return () => controller.abort()
  }, [request, history.document_id])
  const available = history.status !== 'deleted' && history.status !== 'expired'
  return <section className="revision-comparison workspace-panel" aria-labelledby="compare-heading">
    <PanelHeading icon={GitCompareArrows} title="Compare revisions" description="See what changed in the saved original text." />
    <h2 id="compare-heading" className="sr-only">Compare revisions</h2>
    {!available ? <p className="field-note">Source content is unavailable. Retained action history is shown below.</p>
      : history.revisions.length < 2 ? <p className="field-note">Save a new source revision to compare it with this one.</p>
      : <>
        <form className="comparison-picker" onSubmit={(event) => {
          event.preventDefault(); setData({ kind: 'loading' }); setRequest({ before, after, attempt: (request?.attempt ?? 0) + 1 })
        }}>
          {(['before', 'after'] as const).map((side) => <div key={side}>
            <label htmlFor={`compare-${side}`}>{side === 'before' ? 'Before' : 'After'}</label>
            <GlassSelect id={`compare-${side}`} value={side === 'before' ? before : after} onValueChange={side === 'before' ? setBefore : setAfter}>
              {history.revisions.map((revision) => <option key={revision.id} value={revision.id}
                data-description={new Date(revision.created_at).toLocaleString()}>
                Revision {revision.number}{revision.is_current ? ' · Current' : ''}
              </option>)}
            </GlassSelect>
          </div>)}
          <button type="submit" disabled={!before || !after || before === after || data.kind === 'loading'}>
            {data.kind === 'loading' ? 'Comparing…' : 'Compare sources'}
          </button>
        </form>
        <p className="field-note">This compares saved source revisions before review decisions. Choose two different revisions.</p>
        {data.kind === 'loading' && <LoadingState label="Loading protected source revisions…" shape="document" description="Preparing the two saved sources for comparison." />}
        {data.kind === 'error' && <InlineNotice error>{data.message} Use Compare sources to retry.</InlineNotice>}
        {data.kind === 'ready' && <ComparisonPanes key={`${data.value.before.id}.${data.value.after.id}`} value={data.value} />}
      </>}
  </section>
}
