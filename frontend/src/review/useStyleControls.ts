import { useState } from 'react'
import type { CategoryDefault, FindingCategory, PreviewView, SourceView, StyleChoice } from '../api/client'
import type { ReviewFinding } from './textSegments'
import { columnDefault } from './csvColumns'

export type ReviewAction = CategoryDefault['action']
export const tokenChoice: StyleChoice = { style: 'token', style_option: null }
const masks: Record<string, readonly FindingCategory[]> = {
  last4: ['phone', 'identifier', 'national_id', 'custom'],
  first_letters: ['person', 'organization', 'location', 'address', 'custom'],
  email_domain: ['email'], email_first: ['email'], url_host: ['url'], secret_prefix: ['secret'],
}
const standInCategories: FindingCategory[] = ['person', 'organization', 'location', 'address', 'email', 'url', 'phone']
export function choiceKey(choice: StyleChoice): string {
  return `${choice.style ?? 'token'}:${choice.style_option ?? ''}`
}
export function presetChoices(category: FindingCategory, action: ReviewAction, region: string): StyleChoice[] {
  const result: StyleChoice[] = [tokenChoice]
  if (action === 'label') {
    if (standInCategories.includes(category) && (category !== 'phone' || ['US', 'CA', 'GB', 'AU'].includes(region))) result.push({ style: 'stand_in', style_option: null })
    if (category === 'date') result.push({ style: 'date_shift', style_option: null })
  } else if (action === 'redact') {
    if (category === 'date') for (const pattern of ['month_year', 'year', 'age_band'] as const) result.push({ style: 'generalize', style_option: pattern })
    else {
      result.push({ style: 'partial_mask', style_option: 'full' })
      for (const [pattern, categories] of Object.entries(masks)) if (categories.includes(category)) result.push({ style: 'partial_mask', style_option: pattern as StyleChoice['style_option'] })
    }
  }
  return result
}
export function availableChoices(preview: PreviewView | null, finding: ReviewFinding, action: ReviewAction): StyleChoice[] {
  return preview?.style_capabilities?.[finding.finding_id]?.[action] ?? [tokenChoice]
}
export function preferredChoice(source: SourceView, finding: ReviewFinding, action: ReviewAction, preview: PreviewView | null): StyleChoice {
  const current = finding.action === action ? { style: finding.style, style_option: finding.style_option } : null
  const defaults = source.category_defaults[finding.category]
  const column = columnDefault(source, finding)
  const requested = current ?? (column?.default_action === action ? column :
    defaults?.action === action ? defaults : tokenChoice)
  return availableChoices(preview, finding, action).find((choice) => choiceKey(choice) === choiceKey(requested)) ?? tokenChoice
}
export function styleLabel(choice: StyleChoice, action: ReviewAction): string {
  const names: Record<string, string> = {
    stand_in: 'Fictional stand-in', date_shift: 'Shift date', full: 'Mask all letters and digits',
    last4: 'Show last four', first_letters: 'Show first letters', email_domain: 'Show email domain',
    email_first: 'Show first character and top-level domain', url_host: 'Show URL scheme and host',
    secret_prefix: 'Show recognized secret prefix', month_year: 'Month and year', year: 'Year only', age_band: 'Age band',
  }
  return choice.style === 'token' || !choice.style ? action === 'label' ? 'Category label' : action === 'redact' ? '[REDACTED]' : 'Original text'
    : names[choice.style_option ?? choice.style] ?? 'Replacement'
}
export function styleDisclosure(choice: StyleChoice): string | null {
  if (choice.style === 'partial_mask') return 'Partial masks keep the format, separators and length. The selected pattern leaves the named characters visible.'
  if (choice.style === 'stand_in') return 'These are fictional replacements. They stay consistent within this document and do not identify real people, organizations, places or contacts.'
  if (choice.style === 'date_shift') return 'Shifted dates keep the time between dates. Anyone who knows one real date can work out the others.'
  if (choice.style === 'generalize') return choice.style_option === 'age_band' ? 'Age is calculated at the document’s creation date. This choice applies only to a marked birth date.' : 'This removes the day. The selected month or year remains visible.'
  return null
}

export function useStyleControls(source: SourceView, finding: ReviewFinding, preview: PreviewView | null) {
  const column = columnDefault(source, finding)
  const [action, setAction] = useState<ReviewAction>(finding.action ?? column?.default_action ?? source.category_defaults[finding.category]?.action ?? source.preferred_action)
  const [selected, setSelected] = useState(() => choiceKey(preferredChoice(source, finding, action, preview)))
  const choices = availableChoices(preview, finding, action)
  const choice = choices.find((item) => choiceKey(item) === selected) ?? tokenChoice
  function changeAction(value: ReviewAction) {
    setAction(value); setSelected(choiceKey(preferredChoice(source, finding, value, preview)))
  }
  return { action, changeAction, choices, choice, selected: choiceKey(choice), setSelected,
    defaultKeepReason: column?.keep_reason ?? undefined }
}
