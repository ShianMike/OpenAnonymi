import * as Tabs from '@radix-ui/react-tabs'
import { Eye, FileText } from 'lucide-react'
import { cn } from '../ui/cn'
import { demoOutput, examples, type DemoDecisions, type DemoExample } from './demoModel'

function SourceText({ example, selectedId, decisions = {}, onSelect }: {
  example: DemoExample; selectedId?: string; decisions?: DemoDecisions; onSelect?: (id: string) => void
}) {
  return <p className="demo-paragraph">{example.parts.map((part, index) => {
    if (typeof part === 'string') return <span key={index}>{part}</span>
    const className = cn('demo-detail', selectedId === part.id && 'is-selected', decisions[part.id] && 'is-decided')
    return <button type="button" className={className} key={part.id}
      aria-label={`Review ${part.category.toLowerCase()}: ${part.text}`} aria-pressed={selectedId === part.id}
      tabIndex={onSelect ? undefined : -1} onClick={() => onSelect?.(part.id)}>{part.text}</button>
  })}</p>
}

export function DemoDocument({ sample, selectedId, decisions, view, onViewChange, onSelect }: {
  sample: DemoExample; selectedId: string; decisions: DemoDecisions; view: string
  onViewChange: (view: string) => void; onSelect: (id: string) => void
}) {
  return (
    <Tabs.Root value={view} onValueChange={onViewChange} className="demo-view">
      <div className="demo-document-header">
        <Tabs.List aria-label="Example views">
          <Tabs.Trigger value="original"><FileText size={14} aria-hidden="true" /> Original</Tabs.Trigger>
          <Tabs.Trigger value="output"><Eye size={14} aria-hidden="true" /> Reviewed output</Tabs.Trigger>
        </Tabs.List>
      </div>
      <div className="demo-document-stack">
        <Tabs.Content forceMount value="original" className="demo-document" aria-label="Original fictional text" aria-hidden={view !== 'original'} inert={view !== 'original'}>
          <p className="demo-document-title">{sample.title}</p>
          <SourceText example={sample} selectedId={selectedId} decisions={decisions} onSelect={onSelect} />
        </Tabs.Content>
        <Tabs.Content forceMount value="output" className="demo-document" aria-label="Fictional reviewed output" aria-hidden={view !== 'output'} inert={view !== 'output'}>
          <p className="demo-document-title">{sample.title}</p>
          <p className="demo-paragraph demo-output-text">{demoOutput(sample.parts, decisions)}</p>
        </Tabs.Content>
        {/* Responsive text sizing keeps every example stable without a fixed height. */}
        {examples.map((example) => <div className="demo-document demo-document-sizing" key={example.id} aria-hidden="true" inert>
          <p className="demo-document-title">{example.title}</p>
          <SourceText example={example} />
        </div>)}
      </div>
    </Tabs.Root>
  )
}
