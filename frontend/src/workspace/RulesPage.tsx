import { useEffect, useState, type FormEvent } from 'react'
import {
  createWorkspacePreset, getWorkspacePresets, updateWorkspacePreset,
  type PresetInput, type PresetView, type SessionView,
} from '../api/client'

type Data = { kind: 'loading' } | { kind: 'error'; message: string } |
  { kind: 'ready'; presets: PresetView[] }

function PresetEditor({ preset, onSave }: {
  preset?: PresetView
  onSave: (value: PresetInput) => Promise<void>
}) {
  const fieldId = preset?.id ?? 'new'
  const [name, setName] = useState(preset?.name ?? '')
  const [email, setEmail] = useState(preset?.categories.includes('email') ?? true)
  const [phone, setPhone] = useState(preset?.categories.includes('phone') ?? true)
  const [phoneRegion, setPhoneRegion] = useState(preset?.phone_region ?? 'PH')
  const [preferredAction, setPreferredAction] = useState<'label' | 'redact'>(
    preset?.preferred_action ?? 'label',
  )
  const [isDefault, setIsDefault] = useState(preset?.is_default ?? false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await onSave({
        name: name.trim(),
        categories: [
          ...(email ? ['email' as const] : []),
          ...(phone ? ['phone' as const] : []),
        ],
        phone_region: phoneRegion,
        preferred_action: preferredAction,
        is_default: isDefault,
      })
      if (!preset) setName('')
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Preset could not be saved.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={(event) => void save(event)}>
      {error && <p role="alert">{error}</p>}
      <label htmlFor={`preset-name-${fieldId}`}>Preset name</label>{' '}
      <input id={`preset-name-${fieldId}`} required maxLength={100} value={name}
        onChange={(event) => setName(event.target.value)} />{' '}
      <fieldset>
        <legend>Automatic suggestions</legend>
        <label><input type="checkbox" checked={email}
          onChange={(event) => setEmail(event.target.checked)} />Email</label>{' '}
        <label><input type="checkbox" checked={phone}
          onChange={(event) => setPhone(event.target.checked)} />Phone</label>
      </fieldset>
      <label htmlFor={`preset-region-${fieldId}`}>Phone region</label>{' '}
      <select id={`preset-region-${fieldId}`} value={phoneRegion}
        onChange={(event) => setPhoneRegion(event.target.value)}>
        <option value="PH">Philippines</option>
        <option value="US">United States</option>
        <option value="GB">United Kingdom</option>
        <option value="CA">Canada</option>
        <option value="AU">Australia</option>
        <option value="IN">India</option>
      </select>{' '}
      <label htmlFor={`preset-action-${fieldId}`}>Preferred replacement action</label>{' '}
      <select id={`preset-action-${fieldId}`} value={preferredAction}
        onChange={(event) => setPreferredAction(event.target.value as 'label' | 'redact')}>
        <option value="label">Label</option>
        <option value="redact">Redact</option>
      </select>{' '}
      <label><input type="checkbox" checked={isDefault}
        onChange={(event) => setIsDefault(event.target.checked)} />Workspace default</label>{' '}
      <button type="submit" disabled={pending || !name.trim()}>
        {pending ? 'Saving…' : preset ? 'Save preset' : 'Create preset'}
      </button>
    </form>
  )
}

export function RulesPage({ session }: { session: SessionView }) {
  const [workspaceId, setWorkspaceId] = useState(session.memberships[0]?.workspace_id ?? '')
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const administrator = session.memberships.some((item) =>
    item.workspace_id === workspaceId && item.role === 'administrator')

  useEffect(() => {
    if (!workspaceId) return
    const controller = new AbortController()
    getWorkspacePresets(workspaceId, controller.signal).then((presets) => {
      if (!controller.signal.aborted) setData({ kind: 'ready', presets })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setData({
        kind: 'error', message: cause instanceof Error ? cause.message : 'Presets could not be loaded.',
      })
    })
    return () => controller.abort()
  }, [workspaceId, attempt])

  return (
    <section aria-labelledby="rules-title">
      <h1 id="rules-title">Rules</h1>
      <p>Presets choose suggestion categories and a preferred action for new reviews. Every finding still needs your decision. Editing a preset does not change saved reviews.</p>
      {session.memberships.length > 1 && (
        <>
          <label htmlFor="rules-workspace">Workspace</label>{' '}
          <select id="rules-workspace" value={workspaceId} onChange={(event) => {
            setWorkspaceId(event.target.value)
            setData({ kind: 'loading' })
          }}>
            {session.memberships.map((item, index) => (
              <option key={item.workspace_id} value={item.workspace_id}>Workspace {index + 1}</option>
            ))}
          </select>
        </>
      )}
      {notice && <p role="status">{notice}</p>}
      {data.kind === 'loading' && <p role="status">Loading presets…</p>}
      {data.kind === 'error' && (
        <div role="alert"><p>{data.message}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button>
        </div>
      )}
      {data.kind === 'ready' && (
        <>
          <h2>Available presets</h2>
          {data.presets.length === 0 && <p>No presets have been saved for this workspace.</p>}
          <ul>{data.presets.map((preset) => (
            <li key={preset.id}>
              <h3>{preset.name}{preset.is_default ? ' — default' : ''}</h3>
              <p>Version {preset.version}. Suggestions: {preset.categories.join(', ') || 'none'}; phone region {preset.phone_region}; preferred action {preset.preferred_action}.</p>
              {administrator && <PresetEditor key={`${preset.id}-${preset.version}`}
                preset={preset} onSave={async (value) => {
                  await updateWorkspacePreset(
                    workspaceId, preset.id, value, preset.version, session.csrf_token,
                  )
                  setNotice('Preset saved. Existing reviews kept their saved settings.')
                  setAttempt((current) => current + 1)
                }} />}
            </li>
          ))}</ul>
          {administrator && (
            <section aria-labelledby="new-preset-title">
              <h2 id="new-preset-title">New preset</h2>
              <PresetEditor onSave={async (value) => {
                await createWorkspacePreset(workspaceId, value, session.csrf_token)
                setNotice('Preset created for this workspace.')
                setAttempt((current) => current + 1)
              }} />
            </section>
          )}
        </>
      )}
    </section>
  )
}
