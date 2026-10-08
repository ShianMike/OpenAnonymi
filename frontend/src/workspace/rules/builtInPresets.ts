import type { FindingCategory, PresetInput, PresetView } from '../../api/client'
import { detectionChoices } from '../../detection/categories'

// Built-ins use the intake API's label default; only saved workspace presets have a database ID.
export const builtInPresets: (PresetInput & { id: string; description: string; categories: FindingCategory[]; preferred_action: 'label' })[] = [
  { id: 'builtin-contact', name: 'Contact details', description: 'A light check for emails and phone numbers.',
    categories: ['email', 'phone'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-people', name: 'People & places', description: 'Keep the story readable with names and places replaced.',
    categories: ['email', 'phone', 'person', 'organization', 'location'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-full', name: 'Full review', description: 'Check all supported detail types before sharing.',
    categories: detectionChoices.map((choice) => choice.category), phone_region: 'PH', preferred_action: 'label', is_default: false },
]

export const findIntakePreset = (id: string, presets: PresetView[]) =>
  presets.find((preset) => preset.id === id) ?? builtInPresets.find((preset) => preset.id === id)

export const workspacePresetId = (id: string) =>
  builtInPresets.some((preset) => preset.id === id) ? null : id || null
