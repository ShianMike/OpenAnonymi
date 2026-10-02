import { regionName } from '../../ui/phoneRegions'
import { ArrowUpRight, Check, EyeOff, Globe2, Mail, Tag } from 'lucide-react'
import type { PresetInput, PresetView } from '../../api/client'
import { PresetDialog } from './PresetDialog'
import { categoryPresentation } from '../../rules/categoryPresentation'

export function PresetCard({
  preset,
  administrator,
  onSave,
}: {
  preset: PresetView
  administrator: boolean
  onSave: (value: PresetInput) => Promise<void>
}) {
  const example = preset.name.startsWith('Example · ')
  const title = example ? preset.name.slice('Example · '.length) : preset.name
  const ActionIcon = preset.preferred_action === 'label' ? Tag : EyeOff
  const Icon = preset.categories.length === 1 && preset.categories[0] === 'email' ? Mail : ActionIcon
  const labelExample = `${(preset.categories[0] ?? 'custom').toUpperCase()}_001`
  return (
    <li className={`preset-summary-card${preset.is_default ? ' is-default' : ''}`}>
      <div className="preset-card-top">
        <span className="preset-card-icon">
          <Icon size={21} strokeWidth={1.5} aria-hidden="true" />
        </span>
        {preset.is_default ? (
          <span className="subtle-badge">
            <Check size={12} aria-hidden="true" /> Workspace default
          </span>
        ) : example ? (
          <span className="preset-example">Example</span>
        ) : null}
      </div>
      <h3>{title}</h3>
      <p className="preset-card-description">
        {preset.preferred_action === 'label'
          ? 'Replace selected details with readable labels.'
          : 'Hide selected details from the shared output.'}
      </p>
      <div className="preset-output-example">
        <span>Example output</span>
        <code>{preset.preferred_action === 'label' ? labelExample : '[REDACTED]'}</code>
      </div>
      <div className="preset-suggestions">
        <span>Look for</span>
        <ul className="preset-categories" aria-label="Suggestion types">
          {preset.categories.map((category) => {
            const { icon: CategoryIcon, label } = categoryPresentation[category]
            return <li key={category}><CategoryIcon size={13} aria-hidden="true" />{label}</li>
          })}
          {preset.categories.length === 0 && <li>Manual findings only</li>}
        </ul>
      </div>
      <dl className="preset-details">
        <div>
          <dt>
            <Globe2 size={14} aria-hidden="true" /> Phone region
          </dt>
          <dd>{preset.categories.includes('phone') ? regionName(preset.phone_region) : 'Not used'}</dd>
        </div>
        <div>
          <dt>
            <ActionIcon size={14} aria-hidden="true" /> Preferred action
          </dt>
          <dd>{preset.preferred_action === 'label' ? 'Label' : 'Redact'}</dd>
        </div>
      </dl>
      <footer>
        <span>Version {preset.version}</span>
        {administrator ? (
          <PresetDialog
            preset={preset}
            onSave={onSave}
            trigger={
              <button type="button" className="quiet-button" aria-label={`Edit ${preset.name}`}>
                Edit preset <ArrowUpRight size={15} aria-hidden="true" />
              </button>
            }
          />
        ) : (
          <span>Available to use</span>
        )}
      </footer>
    </li>
  )
}
