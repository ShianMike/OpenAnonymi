import { phoneRegions } from '../../ui/phoneRegions'
import { Clock3, SlidersHorizontal } from 'lucide-react'
import { GlassSelect } from '../../ui/GlassSelect'
import { ChoiceSwitch, InlineNotice, PanelHeading } from '../../ui/WorkspaceControls'
import type { IntakeController } from './useIntake'
import { extraDetection, extras } from '../../detection/categories'
import { LoadingState } from '../../loading/LoadingState'

export function IntakeOptions({ intake }: { intake: IntakeController }) {
  const { defaults, pending } = intake
  return (
    <div className="intake-setup-panel workspace-panel">
      <PanelHeading icon={SlidersHorizontal} title="Review setup" description="Your rules. Your decisions." />
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
          <div className="intake-detection-options">
            <p className="intake-mini-heading">LOOK FOR</p>
            <ChoiceSwitch
              label="Email addresses"
              description="Personal and work emails"
              checked={intake.emailEnabled}
              onChange={intake.setEmailEnabled}
              disabled={!!intake.presetId || pending}
            />
            <ChoiceSwitch
              label="Phone numbers"
              description="Numbers in your selected region"
              checked={intake.phoneEnabled}
              onChange={intake.setPhoneEnabled}
              disabled={!!intake.presetId || pending}
            />
            {intake.presetId && (
              <p className="field-note">From your preset. Choose Custom settings to change these.</p>
            )}
            {extraDetection.map((choice) => <ChoiceSwitch key={choice.category} label={choice.label}
              description={choice.description} checked={intake.extraCategories.includes(choice.category)}
              disabled={!!intake.presetId || pending} onChange={(checked) => intake.setExtraCategories((current) =>
                checked ? [...current, choice.category] : current.filter((category) => category !== choice.category))} />)}
            <p className="field-note">Name and place suggestions use an English model on this server. It can miss or misclassify details; you still review the full text.</p>
          </div>
          <div>
            <label className="field-label" htmlFor="phone-region">
              Phone region
            </label>
            <GlassSelect
              id="phone-region"
              value={intake.phoneRegion}
              onValueChange={intake.setPhoneRegion}
              disabled={!!intake.presetId || pending || !intake.phoneEnabled}
            >
              {phoneRegions.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </GlassSelect>
          </div>
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
