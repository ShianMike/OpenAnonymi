import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowUpRight, Plus } from 'lucide-react'
import { createWorkspacePreset, getWorkspacePresets, updateWorkspacePreset, type PresetInput, type PresetView, type SessionView } from '../api/client'
import { GlassSelect } from '../ui/GlassSelect'
import { InlineNotice } from '../ui/WorkspaceControls'
import { LoadingState } from '../loading/LoadingState'
import { PresetDialog } from './rules/PresetDialog'
import { PresetCard } from './rules/PresetCard'
import { builtInPresets } from './rules/builtInPresets'
import { RuleDialog } from '../rules/RuleDialog'
import { RuleLibrary } from '../rules/RuleLibrary'
import { DetectionRules } from '../rules/DetectionRules'
import { getRules, type RuleView } from '../rules/api'
import { categoryPresentation } from '../rules/categoryPresentation'
import './rules/rules.css'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; presets: PresetView[]; rules: RuleView[] }

export function RulesPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const workspaceId = session.memberships.find(item => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? ''
  const requestedView = params.get('view')
  const view = requestedView === 'workspace' || requestedView === 'presets' ? requestedView : 'library'
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState('')
  const activeTab = useRef<HTMLButtonElement>(null)
  const focusAfterReload = useRef(false)
  const administrator = session.memberships.some(item => item.workspace_id === workspaceId && item.role === 'administrator')
  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    Promise.all([getWorkspacePresets(workspaceId, controller.signal), getRules(workspaceId, controller.signal)])
      .then(([presets, rules]) => {
        if (controller.signal.aborted) return
        setData({ kind: 'ready', presets, rules })
        if (focusAfterReload.current) { focusAfterReload.current = false; requestAnimationFrame(() => activeTab.current?.focus()) }
      })
      .catch(cause => { if (!controller.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'Workspace rules could not be loaded.' }) })
    return () => controller.abort()
  }, [workspaceId, attempt])
  function refresh() { focusAfterReload.current = true; setData({ kind: 'loading' }); setAttempt(current => current + 1) }
  function changeView(value: string) {
    setParams(current => { const next = new URLSearchParams(current); if (value === 'library') next.delete('view'); else next.set('view', value); return next }, { replace: true })
  }
  async function create(value: PresetInput) {
    await createWorkspacePreset(workspaceId, value, session.csrf_token)
    setNotice('Preset saved. It is available when starting a new review.'); refresh()
  }
  return <section className="rules-page" aria-labelledby="rules-title">
    <header className="rules-page-heading"><div><h1 id="rules-title">Rules</h1><p>Choose what your reviews look for. Reuse the setup that works for your team.</p></div>
      {administrator && <RuleDialog workspace={workspaceId} csrf={session.csrf_token} saved={() => { setNotice('Rule saved. New reviews use it; existing reviews keep their saved rules.'); refresh() }} trigger={<button type="button" className="rules-button rules-button-primary"><Plus size={15} aria-hidden="true" />Create rule</button>} />}
    </header>
    {session.memberships.length > 1 && <div className="rules-workspace-picker"><label htmlFor="rules-workspace">Workspace</label><GlassSelect id="rules-workspace" value={workspaceId} onValueChange={value => {
      setData({ kind: 'loading' }); setNotice(''); setParams(current => { const next = new URLSearchParams(current); next.set('workspace', value); return next })
    }}>{session.memberships.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.workspace_name || 'Workspace'}</option>)}</GlassSelect></div>}
    <Tabs.Root value={view} onValueChange={changeView} className="rules-tabs">
      <Tabs.List className="rules-tab-list" aria-label="Rules views"><Tabs.Trigger value="library" ref={view === 'library' ? activeTab : undefined}>Rule library</Tabs.Trigger><Tabs.Trigger value="workspace" ref={view === 'workspace' ? activeTab : undefined}>Workspace rules{data.kind === 'ready' && data.rules.length > 0 && <span>{data.rules.length}</span>}</Tabs.Trigger><Tabs.Trigger value="presets" ref={view === 'presets' ? activeTab : undefined}>Review presets</Tabs.Trigger></Tabs.List>
      {notice && <p className="rules-save-notice" role="status">{notice}</p>}
      {data.kind === 'error' && <InlineNotice error title="Workspace rules are unavailable" actions={<button type="button" onClick={refresh}>Retry workspace settings</button>}>{data.message}</InlineNotice>}
      <Tabs.Content value="library" className="rules-tab-content"><RuleLibrary workspace={workspaceId} csrf={session.csrf_token} administrator={administrator}
        rules={data.kind === 'ready' ? data.rules : null} onPresets={() => changeView('presets')} saved={() => { setNotice('Rule saved. New reviews use it; existing reviews keep their saved rules.'); refresh() }} /></Tabs.Content>
      <Tabs.Content value="workspace" className="rules-tab-content">
        {data.kind === 'loading' && <LoadingState label="Loading workspace rules…" shape="list" onRetry={refresh} />}
        {data.kind === 'ready' && <DetectionRules workspace={workspaceId} csrf={session.csrf_token} administrator={administrator} rules={data.rules} saved={() => { setNotice('Workspace rule updated. Existing reviews keep their saved rules.'); refresh() }} onLibrary={() => changeView('library')} />}
      </Tabs.Content>
      <Tabs.Content value="presets" className="rules-tab-content">
        <section className="rules-workspace-presets" aria-labelledby="workspace-presets-title">
          <div className="rules-section-intro"><div><h2 id="workspace-presets-title">Saved for your workspace</h2><p>{administrator ? 'Reusable review settings. Set a default or keep a setup for a particular kind of document.' : 'Review settings saved by your administrator. Everyone in the workspace can use them.'}</p></div>
            {administrator && data.kind === 'ready' && <PresetDialog trigger={<button type="button" className="rules-button"><Plus size={14} aria-hidden="true" />Create preset</button>} onSave={create} />}</div>
          {data.kind === 'loading' && <LoadingState label="Loading saved presets…" shape="list" onRetry={refresh} />}
          {data.kind === 'ready' && (data.presets.length ? <ul className="workspace-preset-list">{data.presets.map(preset => <PresetCard key={preset.id} preset={preset} workspace={workspaceId} administrator={administrator} onSave={async value => {
            await updateWorkspacePreset(workspaceId, preset.id, value, preset.version, session.csrf_token); setNotice('Preset updated. Existing reviews keep their saved settings.'); refresh()
          }} />)}</ul> : <div className="rules-preset-empty"><strong>No saved presets yet</strong><p>Choose a built-in below, or save your own combination of categories and replacement defaults.</p></div>)}
        </section>
        <section aria-labelledby="built-in-presets-title"><div className="rules-section-intro"><div><h2 id="built-in-presets-title">Built-in review presets</h2><p>A starting point for common documents. Review and adjust the categories before scanning.</p></div><span>{builtInPresets.length} available</span></div>
          <ul className="builtin-preset-list">{builtInPresets.map(preset => <li key={preset.id}><article className="builtin-preset-item"><h3>{preset.name}</h3><p>{preset.description}</p>
            <details className="preset-settings"><summary>{preset.categories.length} detection categories</summary><ul className="preset-categories">{preset.categories.map(category => <li key={category}>{categoryPresentation[category].label}</li>)}</ul></details>
            <footer><Link className="rules-button" aria-label={`Use ${preset.name}`} to={`/new?workspace=${workspaceId}&preset=${preset.id}`}>Start review<ArrowUpRight size={14} aria-hidden="true" /></Link>
              {administrator && data.kind === 'ready' && <PresetDialog initial={{ ...preset, name: `${preset.name} (custom)` }} trigger={<button type="button" className="rules-text-button" aria-label={`Customize ${preset.name}`}>Save a copy</button>} onSave={create} />}</footer>
          </article></li>)}</ul>
        </section>
      </Tabs.Content>
    </Tabs.Root>
    <p className="rules-footnote">Rules suggest matches. Presets choose categories and starting settings. You decide what changes before sharing.</p>
  </section>
}
