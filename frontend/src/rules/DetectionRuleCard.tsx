import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { saveRule, type RuleView } from './api'
import { categoryPresentation } from './categoryPresentation'
import { RuleDialog } from './RuleDialog'
import { ChoiceSwitch, InlineNotice } from '../ui/WorkspaceControls'

export function DetectionRuleCard({ rule, workspace, csrf, administrator, saved }: {
  rule: RuleView; workspace: string; csrf: string; administrator: boolean; saved: () => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
    <RuleDialog workspace={workspace} csrf={csrf} rule={rule} editable={administrator} saved={saved}
      trigger={<button type="button" className="rule-summary-copy" disabled={pending} aria-label={`${administrator ? 'Edit' : 'Test'} ${rule.name}`}>
        <strong>{rule.name}</strong><code>{rule.expression}</code><span>{rule.kind === 'phrase' ? 'Exact phrase' : 'ID pattern'} · {categoryPresentation[rule.category].label} · Version {rule.version}</span><ChevronRight size={15} aria-hidden="true" />
      </button>} />
    <div className="rule-summary-actions">
      <span className="rule-state" aria-hidden="true">{rule.enabled ? 'Enabled' : 'Disabled'}</span>
      {administrator ? <ChoiceSwitch label={`Enable ${rule.name}`} checked={rule.enabled} disabled={pending} onChange={(enabled) => void toggle(enabled)} /> :
        <span className="sr-only">{rule.enabled ? 'Enabled' : 'Disabled'}</span>}
    </div>
    {error && <InlineNotice error title="Check the saved rules" actions={<button type="button" onClick={() => { setError(null); saved() }}>Reload rules</button>}>{error}</InlineNotice>}
  </li>
}
