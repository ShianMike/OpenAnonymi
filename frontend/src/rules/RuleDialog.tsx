import { Fragment, useId, useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Check, FlaskConical, Hash, Quote } from 'lucide-react'
import { categoryPresentation, findingCategories } from './categoryPresentation'
import { GlassSelect } from '../ui/GlassSelect'
import { GlassTextarea } from '../ui/GlassTextarea'
import { ChoiceSwitch, DialogFrame, InlineNotice } from '../ui/WorkspaceControls'
import { saveRule, testRule, type RuleInput, type RuleTestView, type RuleView } from './api'

const empty: RuleInput = { name: '', kind: 'phrase', expression: '', category: 'custom',
  case_sensitive: false, whole_word: true, enabled: true }

export function RuleTestPreview({ text, result }: { text: string; result: RuleTestView }) {
  const characters = Array.from(text)
  return <div className="rule-test-result">
    <p className="rule-test-count" role="status"><Check size={16} aria-hidden="true" />
      <strong>{result.match_count} match{result.match_count === 1 ? '' : 'es'} found</strong></p>
    {result.matches.length > 0 ? <div className="rule-match-preview">{result.matches.map((match, index) => {
      const before = characters.slice(index ? result.matches[index - 1].span.end : 0, match.span.start).join('')
      return <Fragment key={match.span.start}>{before}<mark>{match.text}</mark></Fragment>
    })}{characters.slice(result.matches.at(-1)?.span.end ?? 0).join('')}</div> :
      <p>No matches here. Try an example containing your phrase or pattern.</p>}
    {result.match_count > result.matches.length && <p>Showing the first {result.matches.length} matches.</p>}
  </div>
}

export function RuleDialog({ workspace, csrf, rule, trigger, saved, editable = true, initialKind = 'phrase' }: {
  workspace: string; csrf: string; rule?: RuleView; trigger: ReactNode; saved: () => void; editable?: boolean
  initialKind?: RuleInput['kind']
}) {
  const [open, setOpen] = useState(false)
  const [body, setBody] = useState<RuleInput>(empty)
  const [text, setText] = useState('')
  const [result, setResult] = useState<RuleTestView | null>(null)
  const [pending, setPending] = useState<'test' | 'save' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const id = useId()
  const valid = !!body.expression.trim()
  function patch(value: Partial<RuleInput>) { setBody((current) => ({ ...current, ...value })); setResult(null); setError(null) }
  async function perform(operation: 'test' | 'save') {
    if (pending || !valid || (operation === 'save' && (!editable || !result))) return
    setPending(operation); setError(null)
    try {
      if (operation === 'save') { await saveRule(workspace, body, csrf, rule); saved(); setOpen(false) }
      else setResult(await testRule(workspace, body, text, csrf))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The rule could not be checked.') }
    finally { setPending(null) }
  }
  function submit(event: FormEvent) { event.preventDefault(); void perform('save') }
  return <Dialog.Root open={open} onOpenChange={(value) => {
    if (pending) return
    if (value) {
      setBody(rule ? { name: rule.name, kind: rule.kind, expression: rule.expression, category: rule.category,
        case_sensitive: rule.case_sensitive, whole_word: rule.whole_word, enabled: rule.enabled } : { ...empty, kind: initialKind })
      setText(rule?.kind === 'identifier' || (!rule && initialKind === 'identifier')
        ? 'A fictional note: CASE-123456 and CASE-654321.' : 'A fictional note about Project Atlas. Another Project Atlas update.')
      setResult(null); setError(null)
    }
    setOpen(value)
  }}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <DialogFrame title={rule ? editable ? 'Edit detection rule' : 'Test detection rule' : 'Create detection rule'}
      description="Choose what to find, then try it on a sample. Matches become suggestions for review."
      busy={!!pending} className="rule-builder-dialog">
      <form onSubmit={submit} className="rule-builder">
        <div className="rule-builder-config">
          <div className="rule-builder-step"><span>1</span><h3>Choose what to find</h3></div>
          <fieldset className="rule-kind-options" disabled={!!pending || !editable}><legend className="sr-only">Match type</legend>
            {(['phrase', 'identifier'] as const).map((kind) => {
              const Icon = kind === 'phrase' ? Quote : Hash
              return <label key={kind} className={body.kind === kind ? 'is-selected' : ''}>
                <input type="radio" name={`${id}-kind`} value={kind} checked={body.kind === kind} onChange={() => patch({ kind })} />
                <Icon size={18} aria-hidden="true" /><strong>{kind === 'phrase' ? 'Exact phrase' : 'ID pattern'}</strong>
                <small>{kind === 'phrase' ? 'Words or a project name' : 'Letters and numbers'}</small>
              </label>
            })}
          </fieldset>
          <div><label className="field-label" htmlFor={`${id}-expression`}>{body.kind === 'identifier' ? 'Pattern to match' : 'Phrase to match'}</label>
            <input id={`${id}-expression`} value={body.expression} maxLength={160} required disabled={!!pending || !editable}
              placeholder={body.kind === 'identifier' ? 'e.g. CASE-######' : 'e.g. Project Atlas'}
              aria-describedby={`${id}-expression-help`} onChange={(event) => patch({ expression: event.target.value })} />
            <p id={`${id}-expression-help`} className="field-note">{body.kind === 'identifier'
              ? <>Use <code>#</code> for a digit and <code>@</code> for a letter. <code>CASE-######</code> finds <code>CASE-123456</code>.</>
              : 'Finds this exact text. Accents and spacing stay significant.'}</p>
          </div>
          <div className="dialog-field-pair">
            <div><label className="field-label" htmlFor={`${id}-category`}>Show matches as</label>
              <GlassSelect id={`${id}-category`} value={body.category} disabled={!!pending || !editable}
                onValueChange={(category) => patch({ category: category as RuleInput['category'] })}>
                {findingCategories.map((category) => <option key={category} value={category}>{categoryPresentation[category].label}</option>)}
              </GlassSelect></div>
            <div><label className="field-label" htmlFor={`${id}-name`}>Rule name <span className="field-optional">Optional</span></label>
              <input id={`${id}-name`} value={body.name} maxLength={80} disabled={!!pending || !editable}
                placeholder="Uses the phrase or pattern" onChange={(event) => patch({ name: event.target.value })} /></div>
          </div>
          <details className="rule-advanced"><summary>Match options</summary>
            <ChoiceSwitch label="Match case" description="Uppercase and lowercase must match." checked={body.case_sensitive ?? false}
              onChange={(case_sensitive) => patch({ case_sensitive })} disabled={!!pending || !editable} />
            <ChoiceSwitch label="Whole words only" description="Avoid matching inside a longer word." checked={body.whole_word ?? true}
              onChange={(whole_word) => patch({ whole_word })} disabled={!!pending || !editable} />
          </details>
          <ChoiceSwitch label="Enabled for new reviews" description="Existing reviews keep their saved rules."
            checked={body.enabled ?? true} onChange={(enabled) => patch({ enabled })} disabled={!!pending || !editable} />
        </div>
        <section className="rule-builder-test" aria-labelledby={`${id}-test-title`}>
          <div className="rule-builder-step"><span>2</span><h3 id={`${id}-test-title`}>Try it on a sample</h3></div>
          <label className="field-label" htmlFor={`${id}-test`}>Sample text</label>
          <GlassTextarea id={`${id}-test`} value={text} rows={5} maxLength={10000} disabled={!!pending}
            onChange={(event) => { setText(event.target.value); setResult(null); setError(null) }} />
          <button type="button" className="rule-test-button" disabled={!!pending || !valid || !text.trim()}
            onClick={() => void perform('test')}><FlaskConical size={17} aria-hidden="true" />{pending === 'test' ? 'Testing…' : 'Test rule'}</button>
          {result ? <RuleTestPreview text={text} result={result} /> : <p className="rule-test-help">Matched text will be highlighted here. Test again after changing the rule.</p>}
        </section>
        <div className="rule-builder-footer">
          {error && <InlineNotice error>{error}</InlineNotice>}
          <p>{editable ? result ? 'Ready to save. Every match still needs a review decision.' : 'Test your rule to enable saving.' : 'You can test this rule. An administrator can change it.'}</p>
          <div className="dialog-actions">
            <Dialog.Close asChild><button type="button" className="quiet-button" disabled={!!pending}>{editable ? 'Cancel' : 'Close'}</button></Dialog.Close>
            {editable && <button type="submit" className="button-primary" disabled={!!pending || !valid || !result}>
              {pending === 'save' ? 'Saving…' : 'Save rule'}</button>}
          </div>
        </div>
      </form>
    </DialogFrame>
  </Dialog.Root>
}
