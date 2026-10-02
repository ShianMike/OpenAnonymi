import type { FindingCategory } from '../api/client'

export const extraDetection = [
  { category: 'person' as const, label: 'People', description: 'English names in context' },
  { category: 'organization' as const, label: 'Organizations', description: 'Company and organization names' },
  { category: 'location' as const, label: 'Places', description: 'Cities, countries and named places' },
  { category: 'identifier' as const, label: 'Identifiers', description: 'IPv4 and payment card checksums' },
]
export const extras = (categories: FindingCategory[]) => categories.filter((category) =>
  extraDetection.some((choice) => choice.category === category))
