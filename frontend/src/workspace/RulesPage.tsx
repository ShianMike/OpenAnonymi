import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowRight, Mail, Plus, ScanLine, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react'
import { createWorkspacePreset, getWorkspacePresets, updateWorkspacePreset,
  type PresetInput, type PresetView, type SessionView } from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { GlassSelect } from '../ui/GlassSelect'
import { InlineNotice } from '../ui/WorkspaceControls'
import { PresetDialog } from './rules/PresetDialog'
import { PresetCard } from './rules/PresetCard'
import { builtInPresets } from './rules/builtInPresets'
import { DetectionRules } from '../rules/DetectionRules'
import { RulesEmptyState, RulesLoading, RulesSectionHeading } from '../rules/RulesSection'
import './rules/rules.css'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; presets: PresetView[] }
const presetIcons = [Mail, Users, ScanLine]

export function RulesPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const [workspaceId, setWorkspaceId] = useState(() => session.memberships.find(item => item.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const administrator = session.memberships.some((item) => item.workspace_id === workspaceId && item.role === 'administrator')

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspacePresets(workspaceId, controller.signal)
      .then((presets) => { if (!controller.signal.aborted) setData({ kind: 'ready', presets }) })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setData({ kind: 'error', message: cause instanceof Error ? cause.message : 'Presets could not be loaded.' })
      })
    return () => controller.abort()
  }, [workspaceId, attempt])

  async function create(value: PresetInput) {
    await createWorkspacePreset(workspaceId, value, session.csrf_token)
    setNotice('Preset saved to this workspace. It is ready to use in a new review.')
    setAttempt((current) => current + 1)
  }

  return <section className="rules-page" aria-labelledby="rules-title">
    <PageHeader title="Rules" titleId="rules-title" description="Set up your next review. Teach it what matters to your team."
      action={session.memberships.length > 1 && <div className="workspace-picker">
        <label htmlFor="rules-workspace">Workspace</label>
        <GlassSelect id="rules-workspace" value={workspaceId} onValueChange={(value) => {
          setWorkspaceId(value); setData({ kind: 'loading' }); setNotice(null)
          setParams(current => { const next = new URLSearchParams(current); next.set('workspace', value); return next })
        }}>{session.memberships.map((item, index) => <option key={item.workspace_id} value={item.workspace_id}>
          {item.workspace_name || `Workspace ${index + 1}`}</option>)}</GlassSelect>
      </div>} />
    <Tabs.Root defaultValue="presets" className="rules-tabs">
      <Tabs.List className="rules-tab-list" aria-label="Rule settings">
        <Tabs.Trigger value="presets"><SlidersHorizontal size={17} aria-hidden="true" />Presets</Tabs.Trigger>
        <Tabs.Trigger value="detection"><ScanLine size={17} aria-hidden="true" />Detection rules</Tabs.Trigger>
      </Tabs.List>
      <Tabs.Content value="presets" className="rules-tab-content">
        <section className="rules-section" aria-labelledby="builtin-presets-title">
          <RulesSectionHeading id="builtin-presets-title" icon={ShieldCheck} title="Start with a built-in"
            description="Ready to use in every workspace. Customize a copy when you need more control." />
          <ul className="rules-card-grid builtin-preset-grid">
            {builtInPresets.map((preset, index) => {
              const Icon = presetIcons[index]
              return <li key={preset.id} className="builtin-preset-card">
                <div className="preset-card-top"><span className="preset-card-icon"><Icon size={20} aria-hidden="true" /></span>
                  <span className="preset-builtin-label">Built-in</span></div>
                <h3>{preset.name}</h3><p>{preset.description}</p>
                <div className="builtin-preset-meta"><span>{preset.categories.length} detail types</span><span>Readable labels</span></div>
                <footer><Link className="button-link" aria-label={`Use ${preset.name}`} to={`/new?workspace=${workspaceId}&preset=${preset.id}`}>
                  Use preset<ArrowRight size={16} aria-hidden="true" /></Link>
                  {administrator && data.kind === 'ready' && <PresetDialog initial={{ ...preset, name: `${preset.name} (custom)` }}
                    trigger={<button type="button" className="quiet-button" aria-label={`Customize ${preset.name}`}>Customize</button>} onSave={create} />}
                </footer>
              </li>
            })}
          </ul>
        </section>
        <section className="rules-section workspace-preset-section" aria-labelledby="workspace-presets-title">
          <RulesSectionHeading id="workspace-presets-title" icon={SlidersHorizontal} title="Workspace presets"
            description={administrator ? 'Your team’s saved setups. Choose one as the default for new reviews.' : 'Setups saved by your administrator. Everyone in this workspace can use them.'}
            count={data.kind === 'ready' ? data.presets.length : undefined}
            action={administrator && data.kind === 'ready' && <PresetDialog
              trigger={<button className="rules-add-button" type="button"><Plus size={16} aria-hidden="true" />Create preset</button>} onSave={create} />} />
          {notice && <InlineNotice>{notice}</InlineNotice>}
          {data.kind === 'loading' && <RulesLoading label="Loading workspace presets…" />}
          {data.kind === 'error' && <InlineNotice error>{data.message} <button type="button" onClick={() => {
            setData({ kind: 'loading' }); setAttempt((value) => value + 1)
          }}>Retry presets</button></InlineNotice>}
          {data.kind === 'ready' && (data.presets.length === 0 ?
            <RulesEmptyState title="Make a setup your own" description={administrator
              ? 'Customize a built-in above, or create a preset for your team. The built-ins are already available in New review.'
              : 'Use a built-in to get started. Your administrator can save a setup for the team here.'} /> :
            <ul className="workspace-preset-list">{data.presets.map((preset) => <PresetCard key={preset.id} preset={preset}
              workspace={workspaceId} administrator={administrator} onSave={async (value) => {
                await updateWorkspacePreset(workspaceId, preset.id, value, preset.version, session.csrf_token)
                setNotice('Preset saved. Existing reviews kept their saved settings.')
                setAttempt((current) => current + 1)
              }} />)}</ul>)}
        </section>
      </Tabs.Content>
      <Tabs.Content value="detection" className="rules-tab-content">
        <DetectionRules key={workspaceId} workspace={workspaceId} csrf={session.csrf_token} administrator={administrator} />
      </Tabs.Content>
    </Tabs.Root>
    <p className="rules-footnote"><ShieldCheck size={16} aria-hidden="true" />Presets and rules suggest a starting point. You make every decision before sharing.</p>
  </section>
}
