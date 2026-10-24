import { Fragment, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import { Check, Play } from 'lucide-react'
import { categoryPresentation, findingCategories } from './categoryPresentation'
import { GlassSelect } from '../ui/GlassSelect'
import { GlassTextarea } from '../ui/GlassTextarea'
import { ChoiceSwitch, DialogFrame, InlineNotice } from '../ui/WorkspaceControls'
import { saveRule, testRule, type RuleInput, type RuleTestView, type RuleView } from './api'
import './rules.css'

const empty: RuleInput = { name: '', kind: 'phrase', expression: '', category: 'custom',
  case_sensitive: false, whole_word: true, enabled: true }

export function RuleTestPreview({ text, result }: { text: string; result: RuleTestView }) {
  const characters = Array.from(text)
  return <div className="rule-test-result">
    <p className="rule-test-count" data-matched={result.match_count > 0 || undefined} role="status">
      {result.match_count > 0 && <Check size={16} aria-hidden="true" />}<strong>{result.match_count} match{result.match_count === 1 ? '' : 'es'} found</strong>
    </p>
    {result.matches.length > 0 ? <div className="rule-match-preview">{result.matches.map((match, index) => {
      const before = characters.slice(index ? result.matches[index - 1].span.end : 0, match.span.start).join('')
      return <Fragment key={match.span.start}>{before}<mark>{match.text}</mark></Fragment>
    })}{characters.slice(result.matches.at(-1)?.span.end ?? 0).join('')}</div>
      : <p>No matches. Check the format or try a sample containing the value you want to find.</p>}
    {result.match_count > result.matches.length && <p>Showing the first {result.matches.length} matches.</p>}
  </div>
}

export function RuleDialog({ workspace, csrf, rule, initial, initialSample, trigger, saved, editable = true, startWithTest = false }: {
  workspace: string; csrf: string; rule?: RuleView; initial?: RuleInput; initialSample?: string
  trigger: ReactNode; saved: () => void; editable?: boolean; startWithTest?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [body, setBody] = useState<RuleInput>(empty)
  const [view, setView] = useState('definition')
  const [text, setText] = useState('')
  const [result, setResult] = useState<RuleTestView | null>(null)
  const [pending, setPending] = useState<'test' | 'save' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const loaded = useRef<string | null>(null)
  const testButton = useRef<HTMLButtonElement>(null)
  const testTab = useRef<HTMLButtonElement>(null)
  const id = useId()
  const valid = !!body.expression.trim() && (body.kind === 'phrase' || /[#@]/.test(body.expression))
  const tested = !!result?.match_count
  function patch(value: Partial<RuleInput>) {
    setBody(current => ({ ...current, ...value }))
    if ('kind' in value || 'expression' in value || 'case_sensitive' in value || 'whole_word' in value) setResult(null)
    setError(null)
  }
  async function perform(operation: 'test' | 'save') {
    if (pending || !valid || (operation === 'save' && (!editable || !tested))) return
    setPending(operation); setError(null)
    try {
      if (operation === 'save') { await saveRule(workspace, body, csrf, rule); loaded.current = null; setOpen(false); saved() }
      else setResult(await testRule(workspace, body, text, csrf))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The rule could not be checked.') }
    finally { setPending(null); if (operation === 'test') requestAnimationFrame(() => testButton.current?.focus()) }
  }
  function submit(event: FormEvent) { event.preventDefault(); void perform('save') }
  return <Dialog.Root open={open} onOpenChange={next => {
    if (pending) return
    const origin = rule ? `${rule.id}:${rule.version}` : 'new'
    if (next && loaded.current !== origin) {
      const definition = rule ?? initial ?? empty
      const sample = definition.expression ? definition.kind === 'identifier' ? definition.expression.replaceAll('#', '1').replaceAll('@', 'A') : definition.expression : 'Project Atlas'
      setBody({ name: definition.name, kind: definition.kind, expression: definition.expression, category: definition.category,
        case_sensitive: definition.case_sensitive, whole_word: definition.whole_word, enabled: definition.enabled })
      setText(initialSample ?? `A fictional note about ${sample}.`)
      setView(startWithTest ? 'test' : 'definition'); setResult(null); setError(null); loaded.current = origin
    }
    setOpen(next)
  }}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <DialogFrame title={rule ? editable ? 'Edit workspace rule' : 'Test workspace rule' : initial ? editable ? 'Add a library rule' : 'Preview library rule' : 'New detection rule'}
      description="Find a phrase or a specific ID format. Matches become suggestions you review."
      busy={!!pending} className="workspace-side-dialog rule-editor-dialog">
      <form onSubmit={submit} className="rule-editor-form">
        <Tabs.Root value={view} onValueChange={setView} className="rule-editor-views">
          <Tabs.List className="rule-editor-tabs" aria-label="Rule editor views">
            <Tabs.Trigger value="definition" disabled={!!pending}>Definition</Tabs.Trigger>
            <Tabs.Trigger ref={testTab} value="test" disabled={!!pending}>Test playground{tested && <Check size={13} aria-hidden="true" />}</Tabs.Trigger>
          </Tabs.List>
          <div className="rule-editor-body">
            <Tabs.Content value="definition" className="rule-definition">
              <div><label className="field-label" htmlFor={`${id}-name`}>Rule name <span className="rule-field-optional">Optional</span></label>
                <input id={`${id}-name`} value={body.name} maxLength={80} disabled={!!pending || !editable} placeholder="Uses the phrase or pattern if blank" onChange={event => patch({ name: event.target.value })} />
              </div>
              <fieldset className="rule-kind-options" disabled={!!pending || !editable}><legend className="field-label">Match type</legend>
                {(['phrase', 'identifier'] as const).map(kind => <label key={kind}><input type="radio" name={`${id}-kind`} checked={body.kind === kind} value={kind} onChange={() => patch({ kind })} /><span>{kind === 'phrase' ? 'Exact phrase' : 'ID pattern'}</span></label>)}
              </fieldset>
              <div><label className="field-label" htmlFor={`${id}-expression`}>{body.kind === 'identifier' ? 'Pattern' : 'Phrase'}</label>
                <input className={body.kind === 'identifier' ? 'rule-pattern-input' : undefined} id={`${id}-expression`} value={body.expression} maxLength={160} required disabled={!!pending || !editable}
                  placeholder={body.kind === 'identifier' ? 'CASE-######' : 'Project Atlas'} aria-describedby={`${id}-pattern-help`} onChange={event => patch({ expression: event.target.value })} />
                <p className="rule-field-note" id={`${id}-pattern-help`}>{body.kind === 'identifier' ? <>Use <code>#</code> for a digit and <code>@</code> for an A–Z letter. All other characters match literally.</> : 'Matches this text exactly. Spacing and accents remain significant.'}</p>
              </div>
              <div><label className="field-label" htmlFor={`${id}-category`}>Finding category</label><GlassSelect id={`${id}-category`} value={body.category} disabled={!!pending || !editable} onValueChange={category => patch({ category: category as RuleInput['category'] })}>
                {findingCategories.map(category => <option key={category} value={category}>{categoryPresentation[category].label}</option>)}
              </GlassSelect></div>
              <div className="rule-option-list">
                <ChoiceSwitch label="Match case" description="Uppercase and lowercase must match." checked={body.case_sensitive ?? false} onChange={case_sensitive => patch({ case_sensitive })} disabled={!!pending || !editable} />
                <ChoiceSwitch label="Whole words only" description="Skip a match inside a longer word or ID." checked={body.whole_word ?? true} onChange={whole_word => patch({ whole_word })} disabled={!!pending || !editable} />
                <ChoiceSwitch label="Enabled for new reviews" description="Existing reviews keep their saved rules." checked={body.enabled ?? true} onChange={enabled => patch({ enabled })} disabled={!!pending || !editable} />
              </div>
            </Tabs.Content>
            <Tabs.Content value="test" className="rule-playground">
              <div className="rule-test-definition"><span>{body.kind === 'identifier' ? 'Pattern' : 'Phrase'}</span><code>{body.expression || 'Nothing defined yet'}</code><button type="button" onClick={() => setView('definition')}>{editable ? 'Edit' : 'View definition'}</button></div>
              <div><label className="field-label" htmlFor={`${id}-sample`}>Sample text</label><p className="rule-field-note">Include a value that should match and a similar one that should not.</p>
                <GlassTextarea id={`${id}-sample`} value={text} rows={6} maxLength={10000} disabled={!!pending} onChange={event => { setText(event.target.value); setResult(null); setError(null) }} />
              </div>
              <div className="rule-test-tools"><span>Up to 10,000 characters</span><button ref={testButton} type="button" className="rules-button" disabled={!!pending || !valid || !text.trim()} onClick={() => void perform('test')}><Play size={14} aria-hidden="true" />{pending === 'test' ? 'Testing…' : 'Run test'}</button></div>
              {result ? <RuleTestPreview text={text} result={result} /> : <div className="rule-test-placeholder"><strong>See exactly what matches</strong><p>Run the test to highlight matching text. Samples are not saved with the rule.</p></div>}
            </Tabs.Content>
          </div>
        </Tabs.Root>
        <footer className="rule-editor-footer">
          {error && <InlineNotice error>{error}</InlineNotice>}
          <p>{editable ? tested ? 'Test passed. Saving applies this rule to new reviews.' : 'Find at least one match in the playground before saving.' : 'You can test this rule. Only an administrator can save changes.'}</p>
          <div>{view === 'definition' && <button type="button" className="rules-button rule-next-test" disabled={!!pending} onClick={() => { setView('test'); testTab.current?.focus() }}>Continue to test<Play size={14} aria-hidden="true" /></button>}
            <Dialog.Close className="rules-button" disabled={!!pending}>{editable ? 'Close' : 'Done'}</Dialog.Close>
            {editable && <button type="submit" className="rules-button rules-button-primary" disabled={!!pending || !valid || !tested}>{pending === 'save' ? 'Saving…' : rule ? 'Save changes' : 'Add to workspace'}</button>}
          </div>
        </footer>
      </form>
    </DialogFrame>
  </Dialog.Root>
}
