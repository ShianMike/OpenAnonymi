import { useEffect, useState } from 'react'
import { Hash, Plus, Quote, ScanText } from 'lucide-react'
import { getRules, type RuleView } from './api'
import { RuleDialog } from './RuleDialog'
import { InlineNotice } from '../ui/WorkspaceControls'
import { RulesEmptyState, RulesLoading, RulesSectionHeading } from './RulesSection'
import { DetectionRuleCard } from './DetectionRuleCard'
import './rules.css'

export function DetectionRules({ workspace, csrf, administrator }: {
  workspace: string
  csrf: string
  administrator: boolean
}) {
  const [rules, setRules] = useState<RuleView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getRules(workspace, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) setRules(rows)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : 'Rules could not be loaded.')
      })
    return () => controller.abort()
  }, [workspace, attempt])
  const saved = () => {
    setError(null)
    setAttempt((value) => value + 1)
  }
  const create = administrator && (
    <RuleDialog
      workspace={workspace} csrf={csrf} saved={saved}
      trigger={<button type="button" className="rules-add-button"><Plus size={16} aria-hidden="true" /> New rule</button>}
    />
  )

  return (
    <section className="rules-section detection-rules" aria-labelledby="detection-rules-title">
      <RulesSectionHeading
        id="detection-rules-title" icon={ScanText} title="Detection rules"
        description="Catch the phrases and identifiers that matter to your team."
        count={rules?.length} action={create}
      />
      {error && <InlineNotice error>{error} <button type="button" onClick={saved}>Retry rules</button></InlineNotice>}
      {!rules && !error && <RulesLoading label="Loading detection rules…" />}
      {rules?.length === 0 && (
        <RulesEmptyState
          title="Look for your team's details"
          description={administrator
            ? 'Add a project name or an identifier pattern. Test it on a sample before saving.'
            : 'Your administrator can add phrases and identifier patterns for your team.'}
        >
          <div className="rule-pattern-examples" role="group" aria-label="Example patterns, not saved rules">
            <p>Example patterns</p>
            <div><Quote size={17} aria-hidden="true" /><span>Exact phrase<code>Project Atlas</code></span></div>
            <div><Hash size={17} aria-hidden="true" /><span>Identifier template<code>CASE-######</code></span></div>
          </div>
        </RulesEmptyState>
      )}
      {rules && rules.length > 0 && (
        <ul className="rules-card-grid detection-rule-grid">
          {rules.map((rule) => (
            <DetectionRuleCard
              key={rule.id} rule={rule} workspace={workspace}
              csrf={csrf} administrator={administrator} saved={saved}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
