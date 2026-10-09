import { useEffect, useState } from 'react'
import { ArrowRight, Hash, Plus, Quote, ScanLine } from 'lucide-react'
import { getRules, type RuleView } from './api'
import { RuleDialog } from './RuleDialog'
import { DetectionRuleCard } from './DetectionRuleCard'
import { RulesEmptyState, RulesLoading, RulesSectionHeading } from './RulesSection'
import { InlineNotice } from '../ui/WorkspaceControls'
import './rules.css'

export function DetectionRules({ workspace, csrf, administrator }: { workspace: string; csrf: string; administrator: boolean }) {
  const [rules, setRules] = useState<RuleView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!workspace) return
    const controller = new AbortController()
    getRules(workspace, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setRules(value) })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Rules could not be loaded.') })
    return () => controller.abort()
  }, [workspace, attempt])
  function saved() { setError(null); setAttempt((value) => value + 1) }
  return <section className="rules-section detection-rules" aria-labelledby="detection-rules-title">
    <RulesSectionHeading id="detection-rules-title" icon={ScanLine} title="Find your team’s details"
      description="Add the names and ID patterns that built-in suggestions may miss."
      action={administrator && <RuleDialog workspace={workspace} csrf={csrf} saved={saved}
        trigger={<button type="button" className="rules-add-button"><Plus size={16} aria-hidden="true" />Create rule</button>} />} />
    {administrator && <div className="rule-starters" aria-label="Create a detection rule">
      {(['phrase', 'identifier'] as const).map((kind) => {
        const Icon = kind === 'phrase' ? Quote : Hash
        return <RuleDialog key={kind} workspace={workspace} csrf={csrf} saved={saved} initialKind={kind}
          trigger={<button type="button" className="rule-starter">
            <span className="rules-section-icon"><Icon size={21} aria-hidden="true" /></span>
            <span><strong>{kind === 'phrase' ? 'Find an exact phrase' : 'Match an ID pattern'}</strong>
              <small>{kind === 'phrase' ? 'A project, client, or internal name.' : 'Case references and team identifiers.'}</small>
              <code>{kind === 'phrase' ? 'Project Atlas' : 'CASE-######'}</code></span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>} />
      })}
    </div>}
    <div className="rules-list-heading"><h3>Workspace rules {rules && <span className="rules-count">{rules.length}</span>}</h3>
      {rules && <span>{rules.filter((rule) => rule.enabled).length} enabled</span>}</div>
    {error && <InlineNotice error>{error} <button type="button" onClick={() => { setError(null); setAttempt((value) => value + 1) }}>Retry rules</button></InlineNotice>}
    {!rules && !error && <RulesLoading label="Loading detection rules…" />}
    {rules?.length === 0 && <RulesEmptyState title="No custom rules yet" description={administrator
      ? 'Choose a phrase or pattern above. You can test it against sample text before saving.'
      : 'Your administrator can add phrases and patterns for the team. Built-in suggestions are still available.'} />}
    {!!rules?.length && <ul className="detection-rule-list">{rules.map((rule) => <DetectionRuleCard key={rule.id}
      rule={rule} workspace={workspace} csrf={csrf} administrator={administrator} saved={saved} />)}</ul>}
  </section>
}
