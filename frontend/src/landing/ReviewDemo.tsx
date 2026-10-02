import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowRight, Check, MousePointer2, RotateCcw } from 'lucide-react'
import { actionNames, detailOutput, examples, type DemoAction, type DemoDecisions, type DemoDetail } from './demoModel'
import { DemoDocument } from './DemoDocument'
import { PrivacyGlyph } from './PrivacyGlyph'
import './demo.css'

const choices: { action: DemoAction; description: string }[] = [
  { action: 'label', description: 'Keep the context' },
  { action: 'redact', description: 'Remove the detail' },
  { action: 'keep', description: 'Leave it as written' },
]

export function ReviewDemo() {
  const [sample, setSample] = useState(examples[0])
  const [selectedId, setSelectedId] = useState('person')
  const [view, setView] = useState('original')
  const [decisions, setDecisions] = useState<DemoDecisions>({})
  const [announcement, setAnnouncement] = useState('')
  const details = sample.parts.filter((part): part is DemoDetail => typeof part !== 'string')
  const selected = details.find((detail) => detail.id === selectedId) ?? details[0]
  const count = details.filter((detail) => decisions[detail.id]).length
  const done = count === details.length

  function choose(action: DemoAction) {
    setDecisions((current) => ({ ...current, [selected.id]: action }))
    setAnnouncement(`${selected.category}: ${actionNames[action]}. Output: ${detailOutput(selected, action)}.`)
  }

  function reset() {
    setDecisions({})
    setSelectedId('person')
    setView('original')
    setAnnouncement('Example reset. Three details are ready for your decisions.')
  }

  return (
    <div id="try-review" className="landing-demo-wrap" data-landing-reveal tabIndex={-1}>
      <div className="landing-demo-back" aria-hidden="true" />
      <div className="landing-demo landing-glass">
        <div className="demo-masthead">
          <span className="demo-symbol"><PrivacyGlyph kind="document" size={30} /></span>
          <div><strong>A little review</strong><span>Fictional text. Nothing here is saved.</span></div>
          <button className="demo-reset" type="button" aria-label="Reset example" onClick={reset}><RotateCcw size={16} aria-hidden="true" /></button>
        </div>
        <Tabs.Root value={sample.id} onValueChange={(id) => {
          setSample(examples.find((example) => example.id === id) ?? examples[0])
          reset()
        }}>
          <Tabs.List className="demo-samples" aria-label="Fictional examples">
            {examples.map((example) => <Tabs.Trigger key={example.id} value={example.id}>{example.name}</Tabs.Trigger>)}
          </Tabs.List>
          <Tabs.Content value={sample.id} className="demo-sample-panel">
        <DemoDocument sample={sample} selectedId={selected.id} decisions={decisions} view={view}
          onViewChange={setView} onSelect={setSelectedId} />
        <div className="demo-decisions">
          <div className="demo-decision-heading"><span>{selected.category}</span><strong>{selected.text}</strong></div>
          <fieldset className="demo-choice-group">
            <legend className="sr-only">How to handle {selected.text}</legend>
            {choices.map(({ action, description }) => <label className="demo-choice" key={action}>
              <input type="radio" name="example-action" value={action} checked={decisions[selected.id] === action} onChange={() => choose(action)} />
              <span><strong>{actionNames[action]}</strong><small>{description}</small></span>
              {decisions[selected.id] === action && <Check size={15} aria-hidden="true" />}
            </label>)}
          </fieldset>
          <div className="demo-result"><span>In your output</span><strong key={`${sample.id}-${selected.id}-${decisions[selected.id]}`}>
            {detailOutput(selected, decisions[selected.id])}</strong></div>
          <p className="demo-keep-note">A real review also asks for your reason for keeping a detail.</p>
        </div>
        <div className="demo-footer">
          <span className="demo-progress" aria-hidden="true">{details.map((detail) => <i key={detail.id} data-decided={Boolean(decisions[detail.id])} />)}</span>
          <span>{count} / {details.length} decided</span>
          {done ? <span className="demo-finished"><PrivacyGlyph kind="shield" size={24} /> Your choices, reflected.</span> : (
            <button type="button" onClick={() => {
              const next = details.find((detail) => !decisions[detail.id] && detail.id !== selected.id) ?? details.find((detail) => !decisions[detail.id])
              if (next) setSelectedId(next.id)
              setView('original')
            }}>Next detail <ArrowRight size={14} aria-hidden="true" /></button>
          )}
        </div>
          </Tabs.Content>
        </Tabs.Root>
      </div>
      <p className="demo-caption"><MousePointer2 size={15} aria-hidden="true" /> Pick a highlighted detail. Decide what belongs.</p>
      <span className="sr-only" role="status">{announcement}</span>
    </div>
  )
}
