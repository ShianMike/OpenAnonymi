import { GlassSelect } from '../ui/GlassSelect'
import { useEffect, useState } from 'react'
import {
  createWorkspacePreset,
  getWorkspacePresets,
  updateWorkspacePreset,
  type PresetView,
  type SessionView,
} from '../api/client'
import { PageHeader } from '../ui/PageHeader'
import { Plus, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { InlineNotice } from '../ui/WorkspaceControls'
import { PresetDialog } from './rules/PresetDialog'
import { PresetCard } from './rules/PresetCard'
import { DetectionRules } from '../rules/DetectionRules'
import { RulesEmptyState, RulesLoading, RulesSectionHeading } from '../rules/RulesSection'
import './rules/rules.css'

type Data =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; presets: PresetView[] }

export function RulesPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const administrator = session.memberships.some(
    (item) => item.workspace_id === workspaceId && item.role === 'administrator',
  )

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspacePresets(workspaceId, controller.signal)
      .then((presets) => {
        if (!controller.signal.aborted) setData({ kind: 'ready', presets })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setData({
            kind: 'error',
            message: cause instanceof Error ? cause.message : 'Presets could not be loaded.',
          })
      })
    return () => controller.abort()
  }, [workspaceId, attempt])

  const create = administrator && data.kind === 'ready' && (
    <PresetDialog
      trigger={<button className="button-primary rules-add-button" type="button"><Plus size={16} aria-hidden="true" /> New preset</button>}
      onSave={async (value) => {
        await createWorkspacePreset(workspaceId, value, session.csrf_token)
        setNotice('Preset created for this workspace.')
        setAttempt((current) => current + 1)
      }}
    />
  )

  return (
    <section className="rules-page" aria-labelledby="rules-title">
      <PageHeader
        title="Rules"
        titleId="rules-title"
        description="A thoughtful starting point for every review."
      />
      {session.memberships.length > 1 && (
        <div className="workspace-picker">
          <label htmlFor="rules-workspace">Workspace</label>{' '}
          <GlassSelect
            id="rules-workspace"
            value={workspaceId}
            onValueChange={(value) => {
              setWorkspaceId(value)
              setData({ kind: 'loading' })
              setNotice(null)
            }}
          >
            {session.memberships.map((item, index) => (
              <option key={item.workspace_id} value={item.workspace_id}>
                {item.workspace_name || `Workspace ${index + 1}`}
              </option>
            ))}
          </GlassSelect>
        </div>
      )}
      <section className="rules-section workspace-preset-section" aria-labelledby="workspace-presets-title">
        <RulesSectionHeading id="workspace-presets-title" icon={SlidersHorizontal} title="Workspace presets"
          description="Choose what to look for and how to handle it in a new review."
          count={data.kind === 'ready' ? data.presets.length : undefined}
          action={create} />
        {notice && <InlineNotice>{notice}</InlineNotice>}
        {data.kind === 'loading' && <RulesLoading label="Loading presets…" />}
        {data.kind === 'error' && (
          <InlineNotice error>{data.message} <button type="button" onClick={() => {
            setData({ kind: 'loading' })
            setAttempt((value) => value + 1)
          }}>Retry presets</button></InlineNotice>
        )}
        {data.kind === 'ready' && <>
          {data.presets.length === 0 && (
            <RulesEmptyState title="Save a setup you'll use again"
              description={administrator ? 'Bring your suggestion types, phone region, and preferred action together in one preset.' : 'Your administrator can create reusable settings for new reviews.'} />
          )}
          {data.presets.length > 0 && <ul className="rules-card-grid preset-card-grid">
            {data.presets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                administrator={administrator}
                onSave={async (value) => {
                  await updateWorkspacePreset(
                    workspaceId,
                    preset.id,
                    value,
                    preset.version,
                    session.csrf_token,
                  )
                  setNotice('Preset saved. Existing reviews kept their saved settings.')
                  setAttempt((current) => current + 1)
                }}
              />
            ))}
          </ul>}
        </>}
      </section>
      <DetectionRules key={workspaceId} workspace={workspaceId} csrf={session.csrf_token} administrator={administrator} />
      <p className="rules-footnote"><ShieldCheck size={16} aria-hidden="true" />Changes apply to new reviews. Saved reviews keep their settings, and you decide every finding.</p>
    </section>
  )
}
