import { useEffect, useState } from 'react'
import { ArrowLeftRight, CircleAlert, GitCompareArrows } from 'lucide-react'
import type { DocumentHistoryView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { GlassSelect } from '../ui/GlassSelect'
import { ListPagination } from '../ui/ListPagination'
import { pageWindow } from '../ui/pagination'
import { ComparisonPanes } from './ComparisonPanes'
import { compareRevisions, type ComparisonView } from './api'
import './comparison.css'

type Data = { pair: string } & ({ kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; value: ComparisonView })
const VERSION_PAGE_SIZE = 8

export function RevisionComparison({ history }: { history: DocumentHistoryView }) {
  const [before, setBefore] = useState(history.revisions[1]?.id ?? history.revisions[0]?.id ?? '')
  const [after, setAfter] = useState(history.revisions[0]?.id ?? '')
  const [page, setPage] = useState(0)
  const [attempt, setAttempt] = useState(0)
  const pair = `${history.document_id}.${before}.${after}`
  const [data, setData] = useState<Data>({ pair, kind: 'loading' })
  const range = pageWindow(history.revisions.length, page, VERSION_PAGE_SIZE)
  const base = history.revisions.find(revision => revision.id === before)
  const target = history.revisions.find(revision => revision.id === after)
  const single = history.revisions.length === 1
  const result = data.pair === pair ? data : { pair, kind: 'loading' as const }
  useEffect(() => {
    if (!before || !after) return
    const controller = new AbortController()
    compareRevisions(history.document_id, before, after, controller.signal)
      .then(value => { if (!controller.signal.aborted) setData({ pair, kind: 'ready', value }) })
      .catch(cause => { if (!controller.signal.aborted) setData({ pair, kind: 'error', message: cause instanceof Error ? cause.message : 'Comparison could not be loaded.' }) })
    return () => controller.abort()
  }, [pair, history.document_id, before, after, attempt])

  function options(disabledId: string) {
    return history.revisions.map(revision => <option key={revision.id} value={revision.id} disabled={revision.id === disabledId}
      data-description={`${new Date(revision.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · ${new Date(revision.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}>Version {revision.number}{revision.is_current ? ' · Current' : ''}</option>)
  }
  return <div className="history-version-workbench" data-empty={!history.revisions.length || undefined}>
    {history.revisions.length > 0 && <aside className="history-version-rail" aria-labelledby="history-versions-heading">
      <div className="history-rail-heading"><h2 id="history-versions-heading">Saved versions</h2><p>{single ? 'Your first saved source.' : 'Choose a version to compare.'}</p></div>
      <fieldset className="history-version-list"><legend className="sr-only">{single ? 'Saved version' : 'Compare from version'}</legend>
        {history.revisions.slice(range.start, range.end).map(revision => <label key={revision.id} className="history-version-row" data-active={revision.id === before || undefined} data-disabled={!single && revision.id === after || undefined}>
          <input className="sr-only" type="radio" name="history-base-version" checked={revision.id === before} disabled={!single && revision.id === after}
            aria-label={`${single ? 'View' : 'Compare from'} version ${revision.number}`} onChange={() => setBefore(revision.id)} />
          <span><strong>Version {revision.number}</strong><time dateTime={revision.created_at} title={new Date(revision.created_at).toLocaleString()}>{new Date(revision.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} · {new Date(revision.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time></span>
          {revision.is_current && <small>Current</small>}
        </label>)}
      </fieldset>
      {history.revisions.length > VERSION_PAGE_SIZE && <ListPagination page={range.page} total={history.revisions.length} pageSize={VERSION_PAGE_SIZE} label="Versions" onPrevious={() => setPage(range.page - 1)} onNext={() => setPage(range.page + 1)} />}
      {history.revision_total > history.revisions.length && <p className="history-limit-note">Latest {history.revisions.length} of {history.revision_total} versions.</p>}
      <p className="history-version-note">Saved versions contain original source text. Review decisions aren’t part of this comparison.</p>
    </aside>}
    <section className="history-version-canvas" aria-label={single ? 'Saved source preview' : 'Version comparison'}>
      {history.revisions.length === 0 ? <div className="history-version-empty"><GitCompareArrows size={26} strokeWidth={1.3} aria-hidden="true" /><h2>No saved versions yet</h2><p>Save source text in the review to create a version.</p></div> : <>
        {single ? <div className="history-source-heading"><h2>Version {target?.number}{target?.is_current && <span>Current</span>}</h2><p>Your saved source. Saving an edit creates another version to compare.</p></div> : <><div className="history-comparison-picker">
          <div className="history-mobile-base"><label htmlFor="history-before">Compare from</label><GlassSelect id="history-before" value={before} displayValue={`Version ${base?.number}`} onValueChange={setBefore}>{options(after)}</GlassSelect></div>
          <div className="history-comparison-base"><span>Compare from</span><strong>Version {base?.number}</strong></div>
          <button type="button" className="history-swap" aria-label="Swap compared versions" title="Swap compared versions" onClick={() => { setBefore(after); setAfter(before) }}><ArrowLeftRight size={16} aria-hidden="true" /></button>
          <div className="history-target-version"><label htmlFor="history-after">Compare with</label><GlassSelect id="history-after" value={after} displayValue={`Version ${target?.number}`} onValueChange={setAfter}>{options(before)}</GlassSelect></div>
        </div>
        <p className="history-comparison-help">Version {base?.number} → Version {target?.number}. Source changes are shown automatically.</p></>}
        {result.kind === 'loading' && <LoadingState label={single ? 'Loading saved source…' : 'Comparing saved sources…'} description="Loading the selected versions." shape={single ? 'page' : 'comparison'} onRetry={() => setAttempt(value => value + 1)} />}
        {result.kind === 'error' && <div className="comparison-error" role="alert"><CircleAlert size={17} aria-hidden="true" /><div><p>{result.message}</p><button type="button" onClick={() => { setData({ pair, kind: 'loading' }); setAttempt(value => value + 1) }}>Try again</button></div></div>}
        {result.kind === 'ready' && (single ? <pre className="history-source-preview" tabIndex={0} aria-label={`Version ${target?.number} source text`}>{result.value.blocks.map(block => block.left_text).join('')}</pre> : <ComparisonPanes key={`${result.value.before.id}.${result.value.after.id}`} value={result.value} />)}
      </>}
    </section>
  </div>
}
