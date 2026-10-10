import { phoneRegions } from '../../ui/phoneRegions'
import { Check, ChevronDown, Clock3, FileText, Info, ScanLine, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { GlassSelect } from '../../ui/GlassSelect'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import type { IntakeController } from './useIntake'
import { detectionChoices, extras } from '../../detection/categories'
import { DetectionControls } from '../../detection/DetectionControls'
import { LoadingState } from '../../loading/LoadingState'
import { builtInPresets, findIntakePreset, workspacePresetId } from '../../workspace/rules/builtInPresets'

export function IntakeOptions({ intake }: { intake: IntakeController }) {
  const { defaults, pending } = intake
  const categories = [
    ...(intake.emailEnabled ? ['email' as const] : []),
    ...(intake.phoneEnabled ? ['phone' as const] : []), ...intake.extraCategories,
  ]
  const selected = detectionChoices.filter((choice) => categories.includes(choice.category))
  const unselected = detectionChoices.filter((choice) => !categories.includes(choice.category))
  function selectPreset(value: string) {
    intake.setPresetId(value)
    const preset = defaults.kind === 'ready' ? findIntakePreset(value, defaults.presets) : undefined
    if (preset) {
      intake.setEmailEnabled(preset.categories.includes('email'))
      intake.setPhoneEnabled(preset.categories.includes('phone'))
      intake.setExtraCategories(extras(preset.categories))
      if (workspacePresetId(value)) intake.setPhoneRegion(preset.phone_region)
    }
  }
  return (
    <div className="intake-setup-panel workspace-panel">
      <PanelHeading icon={SlidersHorizontal} title="Review options" description="Choose what to check." />
      {defaults.kind === 'loading' && <LoadingState label="Loading workspace settings…" shape="form" />}
      {defaults.kind === 'error' && (
        <>
          <InlineNotice error>{defaults.message}</InlineNotice>
          <button type="button" onClick={() => intake.setAttempt((value) => value + 1)}>
            Retry settings
          </button>
        </>
      )}
      {defaults.kind === 'ready' && (
        <>
          <fieldset className="intake-coverage-presets" disabled={pending}>
            <legend className="field-label">Scan coverage</legend>
            {builtInPresets.map((preset) => <button type="button" key={preset.id}
              aria-pressed={intake.presetId === preset.id || (!intake.presetId &&
                preset.categories.slice().sort().join(',') === categories.slice().sort().join(','))}
              onClick={() => selectPreset(preset.id)}>
              <span><strong>{preset.name}</strong>
                <small>{preset.id === 'builtin-contact' ? 'Emails and phone numbers'
                  : preset.id === 'builtin-people' ? 'Contacts, names and places'
                  : 'All 11 supported categories'}</small></span>
              <Check size={16} className="intake-preset-check" aria-hidden="true" />
            </button>)}
          </fieldset>
          {defaults.presets.length > 0 && <div>
            <label className="field-label" htmlFor="intake-preset">Workspace preset</label>
            <GlassSelect id="intake-preset" value={workspacePresetId(intake.presetId) ?? ''}
              disabled={pending} onValueChange={selectPreset}>
              <option value="">Quick or custom coverage</option>
              {defaults.presets.map((preset) => <option key={preset.id} value={preset.id}
                data-description={preset.is_default ? 'Workspace default'
                  : `${preset.preferred_action === 'label' ? 'Replace' : 'Hide'} private details`}>
                {preset.name}
              </option>)}
            </GlassSelect>
          </div>}
          <div className="intake-coverage-summary" aria-live="polite">
            <div className="intake-coverage-heading"><strong>Will check</strong>
              <span>{selected.length} {selected.length === 1 ? 'category' : 'categories'}</span></div>
            {selected.length ? <ul className="scan-categories" aria-label="Categories to scan">
              {selected.map((choice) => <li key={choice.category}>{choice.label}</li>)}
            </ul> : <p className="field-note">Manual findings only</p>}
            {unselected.length > 0 && <p className="field-note">Not checked: {unselected.map((choice) => choice.label).join(', ')}.</p>}
          </div>
          <details className="intake-detection-options">
            <summary>
              <ScanLine size={18} aria-hidden="true" />
              <span><strong>Customize categories</strong></span>
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <p className="field-note">Changing a category switches to custom coverage with readable labels.</p>
            <DetectionControls prefix="intake" categories={categories} disabled={pending}
              disabledReason={pending ? 'Wait for this review to finish saving.' : undefined}
              onChange={(categories) => {
                intake.setPresetId('')
                intake.setEmailEnabled(categories.includes('email'))
                intake.setPhoneEnabled(categories.includes('phone'))
                intake.setExtraCategories(extras(categories))
              }} />
            <details className="intake-detection-help intake-help">
              <summary><Info size={17} aria-hidden="true" /><span>About these suggestions</span><ChevronDown size={16} aria-hidden="true" /></summary>
              <ul className="intake-help-list">
                <li><FileText size={17} aria-hidden="true" /><div><strong>English names and places</strong><p>These suggestions work with text written in English.</p></div></li>
                <li><ShieldCheck size={17} aria-hidden="true" /><div><strong>You make the final check</strong><p>Some details may be missed. Read the full text and mark anything else you want to hide.</p></div></li>
              </ul>
              <details className="intake-technical-help">
                <summary>Supported ID numbers <ChevronDown size={14} aria-hidden="true" /></summary>
                <dl>
                  <div><dt>United States</dt><dd>Social Security numbers with hyphens.</dd></div>
                  <div><dt>United Kingdom</dt><dd>National Insurance numbers.</dd></div>
                  <div><dt>Singapore</dt><dd>NRIC and FIN numbers. Numbers starting with M are checked for format only.</dd></div>
                  <div><dt>Malaysia</dt><dd>MyKad numbers with hyphens.</dd></div>
                </dl>
              </details>
            </details>
          </details>
          <details className="intake-detection-options intake-more-options">
            <summary>
              <Clock3 size={18} aria-hidden="true" />
              <span><strong>Region & retention</strong>
                <small>{(intake.phoneEnabled || intake.extraCategories.includes('date')) &&
                  `${phoneRegions.find(([code]) => code === intake.phoneRegion)?.[1] ?? intake.phoneRegion} · `}
                  {intake.retentionDays} day{intake.retentionDays > 1 ? 's' : ''}</small></span>
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <div>
              <label className="field-label" htmlFor="phone-region">
                {intake.extraCategories.includes('date') ? 'Phone and date region' : 'Phone region'}
              </label>
              <GlassSelect
                id="phone-region"
                value={intake.phoneRegion}
                onValueChange={intake.setPhoneRegion}
                disabled={!!workspacePresetId(intake.presetId) || pending || (!intake.phoneEnabled && !intake.extraCategories.includes('date'))}
              >
                {phoneRegions.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </GlassSelect>
            </div>
            {intake.extraCategories.includes('date') && <p className="field-note">Dates like 03/04 mean March 4 in the US and 3 April elsewhere. Month names and address words must be in English.</p>}
            <div className="intake-retention">
              <label className="field-label" htmlFor="retention-days">Keep this review for</label>
              <GlassSelect
                id="retention-days"
                value={intake.retentionDays}
                onValueChange={(value) => intake.setRetentionDays(Number(value))}
                disabled={pending}
              >
                {Array.from({ length: defaults.value.content_retention_days }, (_, index) => index + 1).map(
                  (days) => (
                    <option key={days} value={days}>
                      {days} day{days > 1 ? 's' : ''}
                    </option>
                  ),
                )}
              </GlassSelect>
            </div>
          </details>
          <p className="field-note intake-expiry">
            Available until around{' '}
            {new Date(
              Date.parse(defaults.value.current_time) + intake.retentionDays * 86_400_000,
            ).toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}
            . You won’t be able to open the text after that.
          </p>
        </>
      )}
    </div>
  )
}
