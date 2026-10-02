import { useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { GlassSelect } from '../ui/GlassSelect'
import { GlassTextarea } from '../ui/GlassTextarea'
import { ChoiceSwitch, DialogFrame, InlineNotice } from '../ui/WorkspaceControls'
import { saveRule, testRule, type RuleInput, type RuleTestView, type RuleView } from './api'

const empty: RuleInput = { name: '', kind: 'phrase', expression: '', category: 'custom',
  case_sensitive: false, whole_word: true, enabled: true }

export function RuleDialog({ workspace, csrf, rule, trigger, saved, editable = true }: {
  workspace: string; csrf: string; rule?: RuleView; trigger: ReactNode; saved: () => void; editable?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [body, setBody] = useState<RuleInput>(empty)
  const [text, setText] = useState('A fictional note: CASE-123456 and project Atlas.')
  const [result, setResult] = useState<RuleTestView | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const id = `rule-${rule?.id ?? 'new'}`
  function patch(value: Partial<RuleInput>) { setBody((current) => ({ ...current, ...value })); setResult(null) }
  async function perform(save: boolean) {
    setPending(true); setError(null)
    try {
      if (save) { await saveRule(workspace, body, csrf, rule); saved(); setOpen(false) }
      else setResult(await testRule(workspace, body, text, csrf))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The rule could not be checked.') }
    finally { setPending(false) }
  }
  function submit(event: FormEvent) { event.preventDefault(); if (editable && !pending) void perform(true) }
  return <Dialog.Root open={open} onOpenChange={(value) => {
    if (pending) return
    if (value) { setBody(rule ?? empty); setResult(null); setError(null) }
    setOpen(value)
  }}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <DialogFrame title={rule ? editable ? 'Edit detection rule' : 'Test detection rule' : 'Create detection rule'}
      description="Test a phrase or identifier template. Matches are suggestions for a person to review." busy={pending}>
      <form onSubmit={submit} className="rule-form">
        <label htmlFor={`${id}-name`}>Rule name</label>
        <input id={`${id}-name`} value={body.name} maxLength={80} required disabled={pending || !editable}
          placeholder="e.g. Case references" onChange={(event) => patch({ name: event.target.value })} />
        <div className="dialog-field-pair">
          <div><label htmlFor={`${id}-kind`}>Match type</label>
            <GlassSelect id={`${id}-kind`} value={body.kind} disabled={pending || !editable}
              onValueChange={(kind) => patch({ kind: kind as RuleInput['kind'] })}>
              <option value="phrase">Exact phrase</option><option value="identifier">Identifier template</option>
            </GlassSelect></div>
          <div><label htmlFor={`${id}-category`}>Finding category</label>
            <GlassSelect id={`${id}-category`} value={body.category} disabled={pending || !editable}
              onValueChange={(category) => patch({ category: category as RuleInput['category'] })}>
              {['custom', 'person', 'organization', 'location', 'address', 'identifier', 'email', 'phone'].map((category) =>
                <option key={category} value={category}>{category[0].toUpperCase() + category.slice(1)}</option>)}
            </GlassSelect></div>
        </div>
        <label htmlFor={`${id}-expression`}>{body.kind === 'identifier' ? 'Template' : 'Phrase'}</label>
        <input id={`${id}-expression`} value={body.expression} maxLength={160} required disabled={pending || !editable}
          placeholder={body.kind === 'identifier' ? 'CASE-######' : 'project Atlas'}
          onChange={(event) => patch({ expression: event.target.value })} />
        <p className="field-note">{body.kind === 'identifier' ? '# matches one digit; @ matches one ASCII letter. Other characters match literally.' : 'Matches literal text; accents and spacing are preserved.'}</p>
        <ChoiceSwitch label="Match case" checked={body.case_sensitive ?? false} onChange={(case_sensitive) => patch({ case_sensitive })} disabled={pending || !editable} />
        <ChoiceSwitch label="Whole words only" checked={body.whole_word ?? true} onChange={(whole_word) => patch({ whole_word })} disabled={pending || !editable} />
        <ChoiceSwitch label="Enabled for new reviews" checked={body.enabled ?? true} onChange={(enabled) => patch({ enabled })} disabled={pending || !editable} />
        <label htmlFor={`${id}-test`}>Test text</label>
        <GlassTextarea id={`${id}-test`} value={text} rows={4} maxLength={10000} disabled={pending}
          onChange={(event) => { setText(event.target.value); setResult(null) }} />
        <button type="button" disabled={pending || !body.expression.trim() || !body.name.trim()}
          onClick={() => void perform(false)}>{pending ? 'Checking…' : 'Test rule'}</button>
        {result && <div className="rule-test-result" role="status"><strong>{result.match_count} matches</strong>
          {result.matches.length > 0 ? <ul>{result.matches.map((match) => <li key={match.span.start}>
            <mark>{match.text}</mark><small>Characters {match.span.start + 1}–{match.span.end}</small></li>)}</ul>
            : <p>No matches in this test text. Try the phrase or template in context.</p>}</div>}
        {error && <InlineNotice error>{error}</InlineNotice>}
        {editable && <div className="dialog-actions"><button type="submit" className="button-primary" disabled={pending}>
          {pending ? 'Saving…' : 'Save rule'}</button></div>}
      </form>
    </DialogFrame>
  </Dialog.Root>
}
