import { ArrowUpRight, Hash, Quote } from 'lucide-react'
import type { RuleView } from './api'
import { categoryPresentation } from './categoryPresentation'
import { RuleDialog } from './RuleDialog'

export function DetectionRuleCard({ rule, workspace, csrf, administrator, saved }: {
  rule: RuleView
  workspace: string
  csrf: string
  administrator: boolean
  saved: () => void
}) {
  const Icon = rule.kind === 'phrase' ? Quote : Hash
  return (
    <li className="workspace-panel detection-rule-card">
      <div className="rule-card-heading">
        <span className="rule-kind"><Icon size={16} aria-hidden="true" />{rule.kind === 'phrase' ? 'Exact phrase' : 'Identifier template'}</span>
        <span className={`rule-state${rule.enabled ? ' is-enabled' : ''}`}>
          <span aria-hidden="true" />{rule.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </div>
      <h3>{rule.name}</h3>
      <div className="rule-expression"><code>{rule.expression}</code></div>
      <footer>
        <span>{categoryPresentation[rule.category].label} <span aria-hidden="true">·</span> Version {rule.version}</span>
        <RuleDialog
          workspace={workspace} csrf={csrf} rule={rule} editable={administrator} saved={saved}
          trigger={<button type="button" className="quiet-button">{administrator ? 'Edit & test rule' : 'Test rule'}<ArrowUpRight size={15} aria-hidden="true" /></button>}
        />
      </footer>
    </li>
  )
}
