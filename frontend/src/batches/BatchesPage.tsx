import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Files, Plus } from 'lucide-react'
import {
  getIntakeDefaults, getWorkspacePresets, type FindingCategory, type IntakeDefaultsView,
  type PresetView, type SessionView,
} from '../api/client'
import { extraDetection } from '../detection/categories'
import { LoadingState } from '../loading/LoadingState'
import { PageHeader } from '../ui/PageHeader'
import { GlassSelect } from '../ui/GlassSelect'
import { ChoiceSwitch, InlineNotice, PanelHeading } from '../ui/WorkspaceControls'
import { phoneRegions } from '../ui/phoneRegions'
import { createBatch, getBatches, type BatchList } from './api'
import './batches.css'

type Setup = { workspace: string; defaults: IntakeDefaultsView; presets: PresetView[]; list: BatchList }

export function BatchesPage({ session }: { session: SessionView }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [workspace, setWorkspace] = useState(() => session.memberships.find((row) => row.workspace_id === params.get('workspace'))?.workspace_id ?? session.memberships[0]?.workspace_id ?? '')
  const [setup, setSetup] = useState<Setup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(false)
  const [name, setName] = useState('')
  const [preset, setPreset] = useState('')
  const [categories, setCategories] = useState<FindingCategory[]>(['email', 'phone'])
  const [region, setRegion] = useState('PH')
  const [retention, setRetention] = useState(1)
  useEffect(() => {
    if (!workspace) return
    const controller = new AbortController()
    Promise.all([getIntakeDefaults(workspace, controller.signal), getWorkspacePresets(workspace, controller.signal), getBatches(workspace, controller.signal)])
      .then(([defaults, presets, list]) => {
        if (controller.signal.aborted) return
        setSetup({ workspace, defaults, presets, list })
        setRetention(defaults.content_retention_days)
        setError(null)
      }).catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Batch settings could not be loaded.')
      })
    return () => controller.abort()
  }, [workspace, attempt])
  const ready = setup?.workspace === workspace ? setup : null
  const selectedPreset = ready?.presets.find((row) => row.id === preset)
  const choices = [{ category: 'email' as const, label: 'Email addresses', description: 'Personal and work emails' },
    { category: 'phone' as const, label: 'Phone numbers', description: 'Numbers in your selected region' }, ...extraDetection]
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready || pending) return
    setPending(true)
    setError(null)
    try {
      const batch = await createBatch({ workspace_id: workspace, name: name || null,
        preset_id: preset || null, categories, phone_region: region, language: 'en', retention_days: retention }, session.csrf_token)
      navigate(`/batches/${batch.id}`)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'The batch could not be created.')
    } finally { setPending(false) }
  }
  return <section className="batches-page" aria-labelledby="batches-title">
    <PageHeader title="Batch reviews" titleId="batches-title" description="Shared setup, careful review of every document." action={<Link to="/documents">Back to documents</Link>} />
    {!workspace ? <InlineNotice>Join a workspace to create a batch.</InlineNotice> : <>
      {session.memberships.length > 1 && <div className="workspace-picker">
        <label htmlFor="batch-workspace">Workspace</label><GlassSelect id="batch-workspace" value={workspace} disabled={pending} onValueChange={(value) => { setWorkspace(value); setPreset('') }}>
          {session.memberships.map((row) => <option value={row.workspace_id} key={row.workspace_id}>{row.workspace_name}</option>)}
        </GlassSelect>
      </div>}
      {error && <InlineNotice error>{error} <button type="button" disabled={pending} onClick={() => setAttempt((value) => value + 1)}>Reload settings</button></InlineNotice>}
      {!ready && !error && <LoadingState label="Loading batch settings…" shape="form" />}
      {ready && <div className="batch-create-layout">
        <form className="workspace-panel batch-create-form" onSubmit={submit}>
          <PanelHeading icon={Plus} title="Create a batch" description="Choose shared settings, then upload up to 20 TXT, PDF, DOCX or CSV files." />
          <label htmlFor="batch-name">Batch name <span className="field-note">(optional)</span></label>
          <input id="batch-name" maxLength={200} value={name} disabled={pending} onChange={(event) => setName(event.target.value)} autoComplete="off" />
          <label htmlFor="batch-preset">Rules preset</label>
          <GlassSelect id="batch-preset" value={preset} disabled={pending} onValueChange={setPreset}>
            <option value="">Custom settings</option>{ready.presets.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </GlassSelect>
          <details className="batch-detection"><summary>Suggestion categories</summary>
            {choices.map((choice) => <ChoiceSwitch key={choice.category} {...choice}
              checked={(selectedPreset?.categories ?? categories).includes(choice.category)} disabled={pending || !!preset}
              onChange={(checked) => setCategories((current) => checked ? [...current, choice.category] : current.filter((value) => value !== choice.category))} />)}
          </details>
          <label htmlFor="batch-region">Phone region</label>
          <GlassSelect id="batch-region" value={selectedPreset?.phone_region ?? region} onValueChange={setRegion} disabled={pending || !!preset}>
            {phoneRegions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </GlassSelect>
          <label htmlFor="batch-retention">Keep content for</label>
          <GlassSelect id="batch-retention" value={retention} disabled={pending} onValueChange={(value) => setRetention(Number(value))}>
            {Array.from({ length: ready.defaults.content_retention_days }, (_, index) => index + 1).map((days) => <option key={days} value={days}>{days} day{days === 1 ? '' : 's'}</option>)}
          </GlassSelect>
          <p className="field-note">Settings are copied into every upload. You review and confirm each document separately.</p>
          <button className="button button-primary" type="submit" disabled={pending}>{pending ? 'Creating…' : 'Create batch'}</button>
        </form>
        <div className="workspace-panel batch-index">
          <PanelHeading icon={Files} title="Your batches" description="Open a batch to resume uploads, scans or review." />
          {ready.list.workspace_total != null && <p className="field-note">Workspace total: {ready.list.workspace_total} active batches</p>}
          {ready.list.own_batches.length === 0 ? <p>No batches yet.</p> : <ul>
            {ready.list.own_batches.map((row) => <li key={row.id}><Link to={`/batches/${row.id}`}>
              <strong>{row.name || 'Untitled batch'}</strong><span>{row.document_count} documents · {new Date(row.created_at).toLocaleDateString()}</span>
            </Link></li>)}
          </ul>}
        </div>
      </div>}
    </>}
  </section>
}
