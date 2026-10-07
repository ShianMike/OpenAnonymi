import type { FindingCategory } from '../api/client'

export const extraDetection = [
  { category: 'person' as const, label: 'People', description: 'People’s names in English text' },
  { category: 'organization' as const, label: 'Organizations', description: 'Company and organization names' },
  { category: 'location' as const, label: 'Places', description: 'Cities, countries and named places' },
  { category: 'identifier' as const, label: 'Identifiers', description: 'IP addresses, international bank account numbers, cards and usernames' },
  { category: 'address' as const, label: 'Addresses', description: 'Street addresses with US, UK or Singapore postal codes' },
  { category: 'date' as const, label: 'Dates', description: 'Calendar dates and dates of birth' },
  { category: 'url' as const, label: 'Web addresses', description: 'Website links, including private codes inside a link' },
  { category: 'secret' as const, label: 'Secrets', description: 'Passwords and access keys marked as such' },
  { category: 'national_id' as const, label: 'National IDs', description: 'Supported ID numbers from the US, UK, Singapore and Malaysia' },
]
export const defaultDetectionCategories: FindingCategory[] = ['email', 'phone']
export const detectionChoices = [
  { category: 'email' as const, label: 'Email addresses', description: 'Personal and work emails' },
  { category: 'phone' as const, label: 'Phone numbers', description: 'Numbers in your selected region' },
  ...extraDetection,
]
export const detectionLanguages = [['en', 'English']] as const
export const languageName = (code: string) => detectionLanguages.find(([value]) => value === code)?.[1] ?? code
export const extras = (categories: FindingCategory[]) => categories.filter((category) =>
  extraDetection.some((choice) => choice.category === category))
