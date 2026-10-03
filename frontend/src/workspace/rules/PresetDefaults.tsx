import type { CategoryDefault } from '../../api/client'
import { categoryPresentation, findingCategories } from '../../rules/categoryPresentation'
import { GlassSelect } from '../../ui/GlassSelect'
import { choiceKey, presetChoices, styleDisclosure, styleLabel, tokenChoice, type ReviewAction } from '../../review/useStyleControls'
import '../../review/style-controls.css'

export function PresetDefaults({ value, onChange, region, disabled }: {
  value: Record<string, CategoryDefault>; onChange: (value: Record<string, CategoryDefault>) => void; region: string; disabled: boolean
}) {
  return <details className="preset-defaults-details"><summary>Per-category replacement defaults</summary>
    <p className="field-note">These choices preselect the controls. Every occurrence still needs your decision. Birth-date options and phone stand-ins appear only where available.</p>
    <div className="preset-defaults">{findingCategories.map((category) => {
      const saved = value[category]
      const action = saved?.action ?? 'label'
      const choices = presetChoices(category, action, region)
      const choice = choices.find((item) => choiceKey(item) === choiceKey(saved ?? tokenChoice)) ?? tokenChoice
      const disclosure = styleDisclosure(choice)
      return <div className="preset-default-row" key={category}>
        <strong>{categoryPresentation[category].label}</strong>
        <div className="preset-default-row-fields">
          <div><label className="field-label" htmlFor={`preset-default-action-${category}`}>Default action for {categoryPresentation[category].label}</label>
            <GlassSelect id={`preset-default-action-${category}`} value={saved?.action ?? 'preferred'} disabled={disabled} onValueChange={(next) => {
              const defaults = { ...value }
              if (next === 'preferred') delete defaults[category]
              else defaults[category] = { action: next as ReviewAction, ...tokenChoice }
              onChange(defaults)
            }}><option value="preferred">Use preferred action</option><option value="label">Label</option><option value="redact">Redact</option><option value="keep">Keep</option></GlassSelect>
          </div>
          <div><label className="field-label" htmlFor={`preset-default-style-${category}`}>Default style for {categoryPresentation[category].label}</label>
            <GlassSelect id={`preset-default-style-${category}`} value={choiceKey(choice)} disabled={disabled || !saved} onValueChange={(next) => {
              const selected = choices.find((item) => choiceKey(item) === next)
              if (selected && saved) onChange({ ...value, [category]: { action: saved.action, ...selected } })
            }}>{choices.map((item) => <option key={choiceKey(item)} value={choiceKey(item)}>{styleLabel(item, action)}</option>)}</GlassSelect>
          </div>
        </div>
        {saved && disclosure && <p className="field-note">{disclosure}</p>}
      </div>
    })}</div>
  </details>
}
