import type { DocumentIndexView, MemberView } from '../../api/client'
import { availableReview } from '../../resume/reviewQueue'
import { documentLabel } from '../../workspace/documents/documentPresentation'

export function assignableReviews(items: DocumentIndexView[], search: string, now: number) {
  const query = search.trim().toLocaleLowerCase()
  return items.filter(item => item.is_owner && item.status !== 'scanning' && availableReview(item, now) &&
    documentLabel(item).toLocaleLowerCase().includes(query))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.id.localeCompare(b.id))
}

export const memberRoles = {
  member: { label: 'Member', description: 'Create and export their own reviews, and work on reviews assigned to them.' },
  administrator: { label: 'Administrator', description: 'Also manage members, workspace rules, retention and security policies.' },
} satisfies Record<MemberView['role'], { label: string; description: string }>

export function memberStatus(member: MemberView): 'active' | 'revoked' | 'disabled' {
  return member.disabled_at ? 'disabled' : member.revoked_at ? 'revoked' : 'active'
}

export const memberStatusLabel = { active: 'Access enabled', revoked: 'Access revoked', disabled: 'Account disabled' }

export function memberInitials(email: string): string {
  return email.split('@')[0].split(/[._+-]+/).filter(Boolean).slice(0, 2).map(part => Array.from(part)[0]).join('').toLocaleUpperCase()
}

export function filteredMembers(members: MemberView[], self: string, view: 'active' | 'inactive', search: string, role: string): MemberView[] {
  return members.filter(member => (memberStatus(member) === 'active') === (view === 'active')
    && (role === 'all' || member.role === role) && member.email.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .sort((a, b) => Number(b.user_id === self) - Number(a.user_id === self)
      || Number(b.role === 'administrator') - Number(a.role === 'administrator') || a.email.localeCompare(b.email))
}
