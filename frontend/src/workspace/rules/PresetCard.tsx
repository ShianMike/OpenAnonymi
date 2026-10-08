import { ArrowRight, Check, EyeOff, Pencil, Tag } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { PresetInput, PresetView } from '../../api/client'
import { categoryPresentation } from '../../rules/categoryPresentation'
import { regionName } from '../../ui/phoneRegions'
import { PresetDialog } from './PresetDialog'

export function PresetCard({ preset, workspace, administrator, onSave }: {
  preset: PresetView; workspace: string; administrator: boolean; onSave: (value: PresetInput) => Promise<void>
}) {
  const Icon = preset.preferred_action === 'label' ? Tag : EyeOff
  return <li className={`preset-summary-card${preset.is_default ? ' is-default' : ''}`}>
    <span className="preset-card-icon"><Icon size={19} aria-hidden="true" /></span>
    <div className="preset-summary-copy">
      <div className="preset-summary-name"><h3>{preset.name}</h3>
        {preset.is_default && <span className="preset-default-badge"><Check size={13} aria-hidden="true" />Default</span>}</div>
      <p>{preset.categories.length} detail types<span aria-hidden="true"> · </span>
        {preset.preferred_action === 'label' ? 'Readable labels' : 'Redacted text'}
        {(preset.categories.includes('phone') || preset.categories.includes('date')) && <> · {regionName(preset.phone_region)}</>}</p>
      <details className="preset-settings"><summary>View settings</summary>
        <ul className="preset-categories">{preset.categories.map((category) => {
          const CategoryIcon = categoryPresentation[category].icon
          return <li key={category}><CategoryIcon size={13} aria-hidden="true" />{categoryPresentation[category].label}</li>
        })}</ul>
        <p>Version {preset.version}. {Object.keys(preset.category_defaults).length > 0
          ? `${Object.keys(preset.category_defaults).length} category defaults saved.` : 'Each detail uses the preferred action.'}
          {preset.column_rules.length > 0 && ` ${preset.column_rules.length} column rules saved.`}</p>
      </details>
    </div>
    <div className="preset-summary-actions">
      <Link className="button-link" aria-label={`Use workspace preset ${preset.name}`} to={`/new?workspace=${workspace}&preset=${preset.id}`}>
        Use preset<ArrowRight size={16} aria-hidden="true" /></Link>
      {administrator && <PresetDialog preset={preset} onSave={onSave}
        trigger={<button type="button" className="quiet-icon" aria-label={`Edit ${preset.name}`}><Pencil size={17} aria-hidden="true" /></button>} />}
    </div>
  </li>
}
