import { useState } from 'react'
import { ArrowUpRight, ChevronRight, Search } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import { detectionChoices } from '../detection/categories'
import { RuleDialog } from './RuleDialog'
import { builtInRuleInput, builtInRules, ruleGroups } from './builtInRules'
import type { RuleView } from './api'

export function RuleLibrary({ workspace, csrf, administrator, rules, saved, onPresets }: {
  workspace: string; csrf: string; administrator: boolean; rules: RuleView[] | null; saved: () => void; onPresets: () => void
}) {
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState(ruleGroups[0])
  const search = query.trim().toLocaleLowerCase()
  const visible = builtInRules.filter(rule => (group === ruleGroups[0] || rule.group === group)
    && `${rule.name} ${rule.description} ${rule.pattern} ${rule.group}`.toLocaleLowerCase().includes(search))
  return <div className="rule-library-layout">
    <section className="rule-library-main" aria-labelledby="rule-library-title">
      <div className="rules-section-intro"><div><h2 id="rule-library-title">Ready-made rules</h2><p>Start with a pattern. Test it, adjust it, then add it to your workspace.</p></div><span>{builtInRules.length} available</span></div>
      <div className="rules-library-tools">
        <label className="rules-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search rule library</span><input type="search" placeholder="Search names or patterns…" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <GlassSelect id="library-rule-group" aria-label="Filter rules by use case" value={group} onValueChange={setGroup}>{ruleGroups.map(value => <option key={value} value={value}>{value}</option>)}</GlassSelect>
      </div>
      <ul className="rule-library-list">{visible.map(template => {
        const existing = rules?.find(rule => rule.kind === 'identifier' && rule.expression === template.pattern && !rule.case_sensitive && rule.whole_word)
        return <li key={template.id}><RuleDialog workspace={workspace} csrf={csrf} rule={existing} initial={builtInRuleInput(template)}
          initialSample={`Fictional record: ${template.example}. Near match: ${template.nearMiss}.`} startWithTest editable={administrator && rules !== null} saved={saved}
          trigger={<button type="button" className="rule-library-item" aria-label={`Preview ${template.name}`} disabled={rules === null}>
            <span className="rule-library-copy"><strong>{template.name}<small className="rule-library-group">{template.group}</small>{existing && <small className="rule-installed">{existing.enabled ? 'Added' : 'Saved · off'}</small>}</strong><span>{template.description}</span></span>
            <code>{template.pattern}</code><ChevronRight size={16} aria-hidden="true" />
          </button>} /></li>
      })}</ul>
      {!visible.length && <div className="rules-empty"><h3>No rules match that search</h3><p>Try a different name, format, or use case.</p><button type="button" className="rules-button" onClick={() => { setQuery(''); setGroup(ruleGroups[0]) }}>Clear filters</button></div>}
      <p className="rules-context-note">These templates match a specific format. They do not verify that an ID exists. Adapt the prefix and length to your own records.</p>
    </section>
    <aside className="rules-library-aside" aria-labelledby="automatic-checks-title">
      <span className="rules-eyebrow">Already included</span><h2 id="automatic-checks-title">Automatic checks</h2><p>Choose these categories in any review or preset. No workspace rule needed.</p>
      <ul>{detectionChoices.map(choice => <li key={choice.category}><strong>{choice.label}</strong><span>{choice.description}</span></li>)}</ul>
      <button type="button" className="rules-aside-link" onClick={onPresets}>Browse review presets<ArrowUpRight size={14} aria-hidden="true" /></button>
      <p className="rules-context-note">Names and address words are checked in English. National ID checks support specific formats from the US, UK, Singapore and Malaysia.</p>
    </aside>
  </div>
}
