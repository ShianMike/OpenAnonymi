import { phoneRegions } from '../../ui/phoneRegions'
import { ChevronDown, Clock3, ScanLine, SlidersHorizontal } from 'lucide-react'
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
      <PanelHeading icon={SlidersHorizontal} title="Review setup" description="Make this review your own." />
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
              Rules preset
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
                Custom settings
              </option>
              {defaults.presets.map((preset) => (
                <option
                  key={preset.id}
                  value={preset.id}
                  data-description={
                    preset.is_default
                      ? 'Workspace default'
                      : `${preset.preferred_action === 'label' ? 'Label' : 'Redact'} sensitive details`
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
              <span><strong>Suggestions <span className="intake-category-count">{selected.length}</span></strong>
                <small>{selected.map((choice) => choice.label).join(', ') || 'Off · You can mark details manually'}</small>
              </span>
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <DetectionControls prefix="intake" categories={categories} disabled={!!intake.presetId || pending}
              disabledReason={pending ? 'Wait for this review to finish saving.' : intake.presetId ? 'From your preset. Choose Custom settings to change these.' : undefined}
              onChange={(categories) => {
                intake.setEmailEnabled(categories.includes('email'))
                intake.setPhoneEnabled(categories.includes('phone'))
                intake.setExtraCategories(extras(categories))
              }} />
            <p className="field-note">Suggestions need your review. Check the full text for details that were missed.</p>
            <details className="intake-detection-help">
              <summary>Detection coverage</summary>
              <p className="field-note">Name and place suggestions support English. National IDs cover hyphenated US SSNs, UK NI numbers, Singapore NRIC/FIN and hyphenated Malaysian MyKad. Singapore M-prefix IDs use format only.</p>
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
          {intake.extraCategories.includes('date') && <p className="field-note">Ambiguous numeric dates use month first for the US and day first elsewhere. Month names and address words are English.</p>}
          <div className="intake-retention">
            <label className="field-label" htmlFor="retention-days">
              <span className="retention-heading">
                <Clock3 size={15} aria-hidden="true" /> Keep content for
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
              Expires around{' '}
              {new Date(
                Date.parse(defaults.value.current_time) + intake.retentionDays * 86_400_000,
              ).toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}
              . Content becomes unavailable after expiry.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
