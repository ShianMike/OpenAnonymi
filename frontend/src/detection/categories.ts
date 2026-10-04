import type { FindingCategory } from '../api/client'

export const extraDetection = [
  { category: 'person' as const, label: 'People', description: 'English names in context' },
  { category: 'organization' as const, label: 'Organizations', description: 'Company and organization names' },
  { category: 'location' as const, label: 'Places', description: 'Cities, countries and named places' },
  { category: 'identifier' as const, label: 'Identifiers', description: 'IP addresses, IBANs, cards, handles and usernames' },
  { category: 'address' as const, label: 'Addresses', description: 'Street addresses with US, UK or Singapore postal codes' },
  { category: 'date' as const, label: 'Dates', description: 'Calendar dates and dates of birth' },
  { category: 'url' as const, label: 'Web addresses', description: 'URLs, including queries containing access tokens' },
  { category: 'secret' as const, label: 'Secrets', description: 'Recognizable credentials and explicit key/value context' },
  { category: 'national_id' as const, label: 'National IDs', description: 'US SSN, UK NI, Singapore NRIC/FIN and Malaysian MyKad' },
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
