import { useState } from 'react'
import { Hash, Pencil, Quote } from 'lucide-react'
import { saveRule, type RuleView } from './api'
import { categoryPresentation } from './categoryPresentation'
import { RuleDialog } from './RuleDialog'
import { ChoiceSwitch, InlineNotice } from '../ui/WorkspaceControls'

export function DetectionRuleCard({ rule, workspace, csrf, administrator, saved }: {
  rule: RuleView; workspace: string; csrf: string; administrator: boolean; saved: () => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const Icon = rule.kind === 'phrase' ? Quote : Hash
  async function toggle(enabled: boolean) {
    if (pending || !administrator) return
    setPending(true); setError(null)
    try {
      await saveRule(workspace, { name: rule.name, kind: rule.kind, expression: rule.expression,
        category: rule.category, case_sensitive: rule.case_sensitive, whole_word: rule.whole_word, enabled }, csrf, rule)
      saved()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The rule could not be updated.') }
    finally { setPending(false) }
  }
  return <li className="detection-rule-card">
    <span className="preset-card-icon"><Icon size={19} aria-hidden="true" /></span>
    <div className="rule-summary-copy"><h4>{rule.name}</h4><code>{rule.expression}</code>
      <p>{rule.kind === 'phrase' ? 'Exact phrase' : 'ID pattern'} · {categoryPresentation[rule.category].label} · Version {rule.version}</p></div>
    <div className="rule-summary-actions">
      <span className="rule-state" aria-hidden="true">{rule.enabled ? 'Enabled' : 'Disabled'}</span>
      {administrator ? <ChoiceSwitch label={`Enable ${rule.name}`} checked={rule.enabled} disabled={pending} onChange={(enabled) => void toggle(enabled)} /> :
        <span className="sr-only">{rule.enabled ? 'Enabled' : 'Disabled'}</span>}
      <RuleDialog workspace={workspace} csrf={csrf} rule={rule} editable={administrator} saved={saved}
        trigger={<button type="button" className="quiet-button" disabled={pending} aria-label={`${administrator ? 'Edit' : 'Test'} ${rule.name}`}>
          <Pencil size={16} aria-hidden="true" />{administrator ? 'Edit & test' : 'Test rule'}</button>} />
    </div>
    {error && <InlineNotice error>{error} <button type="button" onClick={() => { setError(null); saved() }}>Reload rules</button></InlineNotice>}
  </li>
}
