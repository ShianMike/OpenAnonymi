import { ChevronDown, Check, Mail, Users, ScanLine } from 'lucide-react'
import { StudioSelect } from '../studio/StudioControls'
import { phoneRegions } from '../../ui/phoneRegions'
import type { IntakeController } from './useIntake'
import { detectionChoices, extras } from '../../detection/categories'
import { builtInPresets, findIntakePreset, workspacePresetId } from '../../workspace/rules/builtInPresets'
import { LoadingState } from '../../loading/LoadingState'

export function IntakeOptions({ intake }: { intake: IntakeController }) {
  const { defaults, pending } = intake
  const categories = [...(intake.emailEnabled ? ['email' as const] : []), ...(intake.phoneEnabled ? ['phone' as const] : []), ...intake.extraCategories]
  function selectPreset(value: string) {
    intake.setPresetId(value)
    const preset = defaults.kind === 'ready' ? findIntakePreset(value, defaults.presets) : undefined
    if (preset) {
      intake.setEmailEnabled(preset.categories.includes('email')); intake.setPhoneEnabled(preset.categories.includes('phone')); intake.setExtraCategories(extras(preset.categories))
      if (workspacePresetId(value)) intake.setPhoneRegion(preset.phone_region)
    }
  }
  if (defaults.kind === 'loading') return <LoadingState label="Loading review settings…" compact onRetry={() => intake.setAttempt(value => value + 1)} />
  if (defaults.kind === 'error') return <div className="studio-settings-loading"><p className="studio-error" role="alert">{defaults.message}</p><button type="button" onClick={() => intake.setAttempt(value => value + 1)}>Retry settings</button></div>
  const regionUsed = intake.phoneEnabled || intake.extraCategories.includes('date')
  return <div className="studio-intake-options">
    <fieldset className="studio-presets" disabled={pending}><legend>Choose your coverage</legend>
      {builtInPresets.filter(preset => ['builtin-contact', 'builtin-people', 'builtin-full'].includes(preset.id)).map(preset => {
        const Icon = preset.id === 'builtin-contact' ? Mail : preset.id === 'builtin-people' ? Users : ScanLine
        const selected = intake.presetId === preset.id || (!intake.presetId && preset.categories.length === categories.length && preset.categories.every(category => categories.includes(category)))
        return <label key={preset.id}><input className="sr-only" type="radio" name="scan-coverage" checked={selected} value={preset.id} onChange={() => selectPreset(preset.id)} /><Icon size={18} strokeWidth={1.5} /><span><strong>{preset.name}</strong><small>{preset.id === 'builtin-contact' ? 'Emails and phone numbers' : preset.id === 'builtin-people' ? 'Contacts, names and places' : 'All 11 supported categories'}</small></span><span className="studio-radio-mark">{selected && <Check size={10} />}</span></label>
      })}
    </fieldset>
    <div className="studio-intake-option"><label className="field-label" htmlFor="intake-preset">All review presets</label><StudioSelect id="intake-preset" value={intake.presetId} disabled={pending} onValueChange={selectPreset}><option value="">Quick or custom coverage</option>{builtInPresets.map(preset => <option key={preset.id} value={preset.id}>{preset.name} · Built-in</option>)}{defaults.presets.map(preset => <option key={preset.id} value={preset.id}>{preset.name} · Workspace</option>)}</StudioSelect></div>
    <details className="studio-customize-categories"><summary><span>Customize categories<small>{categories.length} of {detectionChoices.length} selected</small></span><ChevronDown size={14} /></summary>
      <div className="studio-category-list">{detectionChoices.map(choice => <label className="studio-category" key={choice.category} title={choice.description}><span>{choice.label}</span><input id={`intake-${choice.category}`} type="checkbox" checked={categories.includes(choice.category)} disabled={pending} onChange={event => {
        const next = event.target.checked ? [...categories, choice.category] : categories.filter(category => category !== choice.category)
        intake.setPresetId(''); intake.setEmailEnabled(next.includes('email')); intake.setPhoneEnabled(next.includes('phone')); intake.setExtraCategories(extras(next))
      }} /></label>)}</div><p className="field-note">{categories.length ? 'Unchecked categories won’t be scanned.' : 'No automatic checks. You can mark details yourself.'}</p>
    </details>
    <div className="studio-intake-option"><label className="field-label" htmlFor="phone-region">{intake.extraCategories.includes('date') ? 'Phone and date region' : 'Phone region'}</label><StudioSelect id="phone-region" value={intake.phoneRegion} onValueChange={intake.setPhoneRegion} disabled={!!workspacePresetId(intake.presetId) || pending || !regionUsed} aria-describedby="intake-region-help">{phoneRegions.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</StudioSelect>
      <p className="field-note" id="intake-region-help">{workspacePresetId(intake.presetId) ? 'Set by your workspace preset.' : regionUsed ? 'Used to interpret local numbers and dates.' : 'Used when checking phone numbers or dates.'}</p>
      {intake.extraCategories.includes('date') && <p className="field-note">03/04 means March 4 in the US and 3 April elsewhere.</p>}
    </div>
    <div className="studio-intake-option"><label className="field-label" htmlFor="retention-days">Keep this review for</label><StudioSelect id="retention-days" value={intake.retentionDays} onValueChange={value => intake.setRetentionDays(Number(value))} disabled={pending} aria-describedby="intake-retention-help">{Array.from({ length: defaults.value.content_retention_days }, (_, index) => index + 1).map(days => <option key={days} value={days}>{days} day{days > 1 ? 's' : ''}</option>)}</StudioSelect>
      <p className="field-note" id="intake-retention-help">Content expires around {new Date(Date.parse(defaults.value.current_time) + intake.retentionDays * 86_400_000).toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}. You won’t be able to open the text after that.</p>
    </div>
    <details className="studio-detection-notes"><summary>What this check covers <ChevronDown size={13} /></summary><p>Names, places, month names and address words are checked in English. Read the full text to catch anything missed.</p><p>Supported national IDs: US Social Security numbers with hyphens, UK National Insurance, Singapore NRIC/FIN, and Malaysian MyKad with hyphens. Singapore IDs starting with M are checked for format only.</p></details>
  </div>
}
