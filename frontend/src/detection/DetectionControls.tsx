import type { FindingCategory } from '../api/client'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { ChoiceSwitch } from '../ui/WorkspaceControls'
import { detectionChoices } from './categories'

/** Every editor presents the same supported categories and descriptions. */
export function DetectionControls({ categories, onChange, disabled, disabledReason, prefix,
  variant = 'switch' }: {
  categories: readonly FindingCategory[]
  onChange: (categories: FindingCategory[]) => void
  disabled?: boolean
  disabledReason?: string
  prefix: string
  variant?: 'switch' | 'checkbox'
}) {
  return <div className="detection-controls">
    {detectionChoices.map(({ category, label, description }) => {
      const change = (checked: boolean) => onChange(detectionChoices
        .filter(choice => choice.category === category ? checked : categories.includes(choice.category))
        .map(choice => choice.category))
      const props = { id: `${prefix}-${category}`, label, description,
        checked: categories.includes(category), disabled, disabledReason }
      return variant === 'checkbox'
        ? <GlassCheckbox key={category} {...props} onCheckedChange={change} />
        : <ChoiceSwitch key={category} {...props} onChange={change} />
    })}
    {disabled && disabledReason && <p className="field-note">{disabledReason}</p>}
  </div>
}
