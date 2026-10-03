import { Building2, CalendarDays, Hash, KeyRound, Link, Mail, MapPin, Phone, Tags, Users, BadgeCheck, type LucideIcon } from 'lucide-react'
import type { FindingCategory } from '../api/client'

export const categoryPresentation = {
  email: { label: 'Email', icon: Mail },
  phone: { label: 'Phone', icon: Phone },
  person: { label: 'People', icon: Users },
  organization: { label: 'Organizations', icon: Building2 },
  location: { label: 'Places', icon: MapPin },
  address: { label: 'Addresses', icon: MapPin },
  identifier: { label: 'Identifiers', icon: Hash },
  custom: { label: 'Custom', icon: Tags },
  date: { label: 'Dates', icon: CalendarDays },
  url: { label: 'Web addresses', icon: Link },
  secret: { label: 'Secrets', icon: KeyRound },
  national_id: { label: 'National IDs', icon: BadgeCheck },
} satisfies Record<FindingCategory, { label: string; icon: LucideIcon }>
export const findingCategories = Object.keys(categoryPresentation) as FindingCategory[]
