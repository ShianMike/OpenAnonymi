import { useState } from 'react'
import { Search } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import type { RuleView } from './api'
import { DetectionRuleCard } from './DetectionRuleCard'
import './rules.css'

export function DetectionRules({ workspace, csrf, administrator, rules, saved, onLibrary }: {
  workspace: string; csrf: string; administrator: boolean; rules: RuleView[]; saved: () => void; onLibrary: () => void
}) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const search = query.trim().toLocaleLowerCase()
  const visible = rules.filter(rule => `${rule.name} ${rule.expression}`.toLocaleLowerCase().includes(search)
    && (status === 'all' || (status === 'enabled' ? rule.enabled : !rule.enabled)))
  return <section className="detection-rules" aria-labelledby="workspace-rules-title">
    <div className="rules-section-intro"><div><h2 id="workspace-rules-title">Your workspace rules</h2><p>Enabled rules are included in new reviews. Existing reviews keep a saved copy.</p></div>{rules.length > 0 && <span>{rules.filter(rule => rule.enabled).length} enabled</span>}</div>
    {rules.length > 0 && <div className="rules-library-tools"><label className="rules-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search workspace rules</span><input type="search" placeholder="Search workspace rules…" value={query} onChange={event => setQuery(event.target.value)} /></label><GlassSelect id="workspace-rule-status" aria-label="Filter workspace rules by status" value={status} onValueChange={setStatus}><option value="all">All statuses</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option></GlassSelect></div>}
    {visible.length ? <ul className="detection-rule-list">{visible.map(rule => <DetectionRuleCard key={rule.id} rule={rule} workspace={workspace} csrf={csrf} administrator={administrator} saved={saved} />)}</ul>
      : <div className="rules-empty"><h3>{rules.length ? 'No rules match these filters' : 'Find the details specific to your team'}</h3><p>{rules.length ? 'Try a different name or show all statuses.' : administrator ? 'Add a ready-made pattern from the library, or create a phrase or ID rule of your own.' : 'Your administrator can add phrases and ID patterns. You can test any saved rule here.'}</p>
        <button type="button" className="rules-button" onClick={rules.length ? () => { setQuery(''); setStatus('all') } : onLibrary}>{rules.length ? 'Clear filters' : 'Browse rule library'}</button></div>}
  </section>
}
