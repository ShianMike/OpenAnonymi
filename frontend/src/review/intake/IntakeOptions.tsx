import { phoneRegions } from '../../ui/phoneRegions'
import { ChevronDown, Clock3, FileText, Info, ScanLine, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { GlassSelect } from '../../ui/GlassSelect'
import { InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import type { IntakeController } from './useIntake'
import { detectionChoices, extras } from '../../detection/categories'
import { DetectionControls } from '../../detection/DetectionControls'
import { LoadingState } from '../../loading/LoadingState'

export function IntakeOptions({ intake }: { intake: IntakeController }) {
  const { defaults, pending } = intake
  const categories = [
    ...(intake.emailEnabled ? ['email' as const] : []),
    ...(intake.phoneEnabled ? ['phone' as const] : []), ...intake.extraCategories,
  ]
  const selected = detectionChoices.filter((choice) => categories.includes(choice.category))
  return (
    <div className="intake-setup-panel workspace-panel">
      <PanelHeading icon={SlidersHorizontal} title="Review options" description="Change these only if you need to." />
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
          <div>
            <label className="field-label" htmlFor="intake-preset">
              Saved settings
            </label>
            <GlassSelect
              id="intake-preset"
              value={intake.presetId}
              disabled={pending}
              onValueChange={(value) => {
                intake.setPresetId(value)
                const preset = defaults.presets.find((item) => item.id === value)
                if (preset) {
                  intake.setEmailEnabled(preset.categories.includes('email'))
                  intake.setPhoneEnabled(preset.categories.includes('phone'))
                  intake.setExtraCategories(extras(preset.categories))
                  intake.setPhoneRegion(preset.phone_region)
                }
              }}
            >
              <option value="" data-description="Choose the suggestions for this review.">
                Choose my own
              </option>
              {defaults.presets.map((preset) => (
                <option
                  key={preset.id}
                  value={preset.id}
                  data-description={
                    preset.is_default
                      ? 'Workspace default'
                      : `${preset.preferred_action === 'label' ? 'Replace' : 'Hide'} private details`
                  }
                >
                  {preset.name}
                </option>
              ))}
            </GlassSelect>
          </div>
          <details className="intake-detection-options">
            <summary>
              <ScanLine size={18} aria-hidden="true" />
              <span><strong>What to look for <span className="intake-category-count">{selected.length}</span></strong>
                <small>{selected.map((choice) => choice.label).join(', ') || 'Off · You can mark details yourself'}</small>
              </span>
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <DetectionControls prefix="intake" categories={categories} disabled={!!intake.presetId || pending}
              disabledReason={pending ? 'Wait for this review to finish saving.' : intake.presetId ? 'Using saved settings. Select Choose my own to change these.' : undefined}
              onChange={(categories) => {
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
          <div>
            <label className="field-label" htmlFor="phone-region">
              {intake.extraCategories.includes('date') ? 'Phone and date region' : 'Phone region'}
            </label>
            <GlassSelect
              id="phone-region"
              value={intake.phoneRegion}
              onValueChange={intake.setPhoneRegion}
              disabled={!!intake.presetId || pending || (!intake.phoneEnabled && !intake.extraCategories.includes('date'))}
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
            <label className="field-label" htmlFor="retention-days">
              <span className="retention-heading">
                <Clock3 size={15} aria-hidden="true" /> Keep this review for
              </span>
            </label>
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
            <p className="field-note">
              Available until around{' '}
              {new Date(
                Date.parse(defaults.value.current_time) + intake.retentionDays * 86_400_000,
              ).toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}
              . You won’t be able to open the text after that.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
