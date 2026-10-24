import { useId } from 'react'
import type { MemberView } from '../../api/client'
import { memberRoles } from './memberPresentation'

export function MemberRoleOptions({ value, onChange, disabled }: {
  value: MemberView['role']; onChange: (role: MemberView['role']) => void; disabled?: boolean
}) {
  const id = useId()
  return <fieldset className="people-role-choices" disabled={disabled}><legend>Workspace role</legend>
    {(['member', 'administrator'] as const).map(role => <label key={role}>
      <input type="radio" name={`${id}-role`} value={role} checked={value === role} onChange={() => onChange(role)} aria-label={memberRoles[role].label} />
      <span><strong>{memberRoles[role].label}</strong><small>{memberRoles[role].description}</small></span>
    </label>)}
  </fieldset>
}
