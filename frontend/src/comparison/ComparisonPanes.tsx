import { useRef, useState } from 'react'
import { ArrowDown, ArrowUp, Columns2 } from 'lucide-react'
import type { ComparisonView } from './api'

export function ComparisonPanes({ value }: { value: ComparisonView }) {
  const [side, setSide] = useState<'before' | 'after'>('after')
  const [selected, setSelected] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  function move(direction: number) {
    const next = selected === 0 ? (direction > 0 ? 1 : value.changes)
      : ((selected - 1 + direction + value.changes) % value.changes) + 1
    setSelected(next)
    const target = scrollRef.current?.querySelector<HTMLElement>(`[data-change="${next}"]`)
    target?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
    target?.focus({ preventScroll: true })
  }
  return <div className="comparison-result">
    <div className="comparison-summary">
      <div className="comparison-stats" role="status">
        <strong>{value.changes === 0 ? 'No source changes' : `${value.changes} changed ${value.changes === 1 ? 'section' : 'sections'}`}</strong>
        <span className="comparison-added">+{value.added_lines} lines added</span>
        <span className="comparison-removed">−{value.removed_lines} lines removed</span>
      </div>
      <div className="comparison-navigation" aria-label="Change navigation">
        <button type="button" onClick={() => move(-1)} disabled={!value.changes} aria-label="Previous change"><ArrowUp size={15} aria-hidden="true" /></button>
        <span aria-live="polite">{selected ? `${selected} of ${value.changes}` : 'Jump to change'}</span>
        <button type="button" onClick={() => move(1)} disabled={!value.changes} aria-label="Next change"><ArrowDown size={15} aria-hidden="true" /></button>
      </div>
    </div>
    {value.coarse && <p className="field-note">Large or repetitive revisions are shown in broader change blocks. All saved source text is included.</p>}
    <fieldset className="comparison-mobile-switch"><legend className="sr-only">Revision to display</legend>
      {(['before', 'after'] as const).map((item) => <label key={item}>
        <input type="radio" name="comparison-side" checked={side === item} onChange={() => setSide(item)} />
        <span>{item === 'before' ? 'Before' : 'After'} · Revision {value[item].number}</span>
      </label>)}
    </fieldset>
    <div className="comparison-scroll" ref={scrollRef} tabIndex={0} aria-label="Compared source revisions with aligned scrolling" data-side={side}>
      <div className="comparison-column-headings" aria-hidden="true">
        <span><strong>Before</strong>Revision {value.before.number}</span><span><strong>After</strong>Revision {value.after.number}</span>
      </div>
      {value.blocks.map((block, index) => <div key={index} className="comparison-block" data-kind={block.kind} data-change={block.change ?? undefined}
        data-selected={selected !== 0 && selected === block.change || undefined} tabIndex={block.change ? -1 : undefined}
        aria-label={block.change ? `Change ${block.change}: ${block.kind}` : undefined}>
        {block.change && <div className="comparison-change-label">Changed section {block.change}</div>}
        <div className="comparison-before">
          <span className="comparison-line" aria-label={`Before line ${block.left_start}`}>{block.left_lines ? block.left_start : '—'}</span>
          <pre>{block.left_text || <span className="comparison-empty">No text in this revision</span>}</pre>
        </div>
        <div className="comparison-after">
          <span className="comparison-line" aria-label={`After line ${block.right_start}`}>{block.right_lines ? block.right_start : '—'}</span>
          <pre>{block.right_text || <span className="comparison-empty">No text in this revision</span>}</pre>
        </div>
      </div>)}
    </div>
    <p className="comparison-legend"><span>− Removed / replaced</span><span>+ Added / replaced</span><span><Columns2 size={14} aria-hidden="true" /> Aligned scrolling</span></p>
  </div>
}
