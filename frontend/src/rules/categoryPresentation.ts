import { Building2, Hash, Mail, MapPin, Phone, Tags, Users, type LucideIcon } from 'lucide-react'
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
} satisfies Record<FindingCategory, { label: string; icon: LucideIcon }>
