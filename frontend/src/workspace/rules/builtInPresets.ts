import type { FindingCategory, PresetInput, PresetView } from '../../api/client'
import { detectionChoices } from '../../detection/categories'

// Built-ins use the intake API's label default; only saved workspace presets have a database ID.
export const builtInPresets: (PresetInput & { id: string; description: string; categories: FindingCategory[]; preferred_action: 'label' })[] = [
  { id: 'builtin-contact', name: 'Contact details', description: 'A light check for emails and phone numbers.',
    categories: ['email', 'phone'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-people', name: 'People & places', description: 'Keep the story readable with names and places replaced.',
    categories: ['email', 'phone', 'person', 'organization', 'location'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-support', name: 'Customer support', description: 'Check contacts, customer references, links and secrets in support conversations.',
    categories: ['email', 'phone', 'person', 'identifier', 'url', 'secret'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-research', name: 'Research interviews', description: 'Look for participant names, contacts, places, addresses and dates in transcripts.',
    categories: ['email', 'phone', 'person', 'organization', 'location', 'address', 'date'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-contracts', name: 'Contracts & agreements', description: 'Check parties, contacts, addresses, dates and supported identifiers.',
    categories: ['email', 'phone', 'person', 'organization', 'address', 'date', 'identifier', 'national_id'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-finance', name: 'Finance & billing', description: 'Check billing contacts, addresses, dates, bank details and labeled references.',
    categories: ['email', 'phone', 'person', 'organization', 'address', 'date', 'identifier'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-technical', name: 'Technical logs', description: 'Look for emails, IP addresses, usernames, links and labeled passwords or keys.',
    categories: ['email', 'identifier', 'url', 'secret'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-hr', name: 'Hiring & HR', description: 'Check people, contact details, addresses, dates and supported national IDs.',
    categories: ['email', 'phone', 'person', 'organization', 'location', 'address', 'date', 'national_id'], phone_region: 'PH', preferred_action: 'label', is_default: false },
  { id: 'builtin-full', name: 'Full review', description: 'Check all supported detail types before sharing.',
    categories: detectionChoices.map((choice) => choice.category), phone_region: 'PH', preferred_action: 'label', is_default: false },
]

export const findIntakePreset = (id: string, presets: PresetView[]) =>
  presets.find((preset) => preset.id === id) ?? builtInPresets.find((preset) => preset.id === id)

export const workspacePresetId = (id: string) =>
  builtInPresets.some((preset) => preset.id === id) ? null : id || null
