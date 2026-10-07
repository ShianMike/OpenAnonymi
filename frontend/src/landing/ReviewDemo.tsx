import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowRight, Check, FileText, Minus, RotateCcw, Tag } from 'lucide-react'
import { actionNames, detailOutput, examples, type DemoAction, type DemoDecisions, type DemoDetail } from './demoModel'
import { DemoDocument } from './DemoDocument'
import './demo.css'

const choices = [
  { action: 'label', Icon: Tag, hint: 'Replace with a placeholder' },
  { action: 'redact', Icon: Minus, hint: 'Remove this detail' },
  { action: 'keep', Icon: Check, hint: 'Leave it as written' },
] as const

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
      <div className="landing-demo">
        <Tabs.Root value={sample.id} onValueChange={(id) => {
          setSample(examples.find((example) => example.id === id) ?? examples[0])
          reset()
        }}>
          <div className="demo-masthead">
            <span className="demo-symbol"><FileText size={18} aria-hidden="true" /></span>
            <div className="demo-intro"><strong>Live preview</strong><span>Fictional · Nothing saved</span></div>
            <Tabs.List className="demo-samples" aria-label="Fictional examples">
              {examples.map((example) => <Tabs.Trigger key={example.id} value={example.id}>{example.name}</Tabs.Trigger>)}
            </Tabs.List>
            <button className="demo-reset" type="button" aria-label="Reset example" onClick={reset}><RotateCcw size={16} aria-hidden="true" /></button>
          </div>
          <Tabs.Content value={sample.id} className="demo-sample-panel">
            <div className="demo-workspace">
              <DemoDocument sample={sample} selectedId={selected.id} decisions={decisions} view={view}
                onViewChange={setView} onSelect={setSelectedId} />
              <div className="demo-decisions">
                <div className="demo-decision-context">
                  <div className="demo-decision-heading"><span>{selected.category}</span><strong>{selected.text}</strong></div>
                  <ArrowRight size={16} aria-hidden="true" />
                  <div className="demo-result" data-decided={Boolean(decisions[selected.id])}><span>Output</span><strong>{decisions[selected.id] ? detailOutput(selected, decisions[selected.id]) : '—'}</strong></div>
                </div>
                <fieldset className="demo-choice-group">
                  <legend className="sr-only">Choose an action for {selected.text}</legend>
                  {choices.map(({ action, Icon, hint }) => <label className="demo-choice" key={action} title={hint}>
                    <input type="radio" name="example-action" value={action} checked={decisions[selected.id] === action} onChange={() => choose(action)} />
                    <Icon size={16} aria-hidden="true" /><span>{actionNames[action]}</span>
                  </label>)}
                </fieldset>
                <p className="demo-keep-note">{decisions[selected.id] === 'keep' ? 'Real reviews ask for a reason to keep a detail.' : ''}</p>
              </div>
            </div>
        <div className="demo-footer">
          <div className="demo-progress-summary"><span className="demo-progress" aria-hidden="true">{details.map((detail) => <i key={detail.id} data-decided={Boolean(decisions[detail.id])}>{decisions[detail.id] ? <Check size={11} aria-hidden="true" /> : null}</i>)}</span>
            <span>{count} / {details.length}<span className="sr-only"> decided</span></span></div>
          {done ? <span className="demo-finished"><Check size={16} aria-hidden="true" /> Done</span> : (
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
      <span className="sr-only" role="status">{announcement}</span>
    </div>
  )
}
