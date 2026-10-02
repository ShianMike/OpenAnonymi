import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { LoadingState } from '../loading/LoadingState'

export function RulesSectionHeading({
  id, icon: Icon, title, description, count, action,
}: {
  id: string
  icon: LucideIcon
  title: string
  description: string
  count?: number
  action?: ReactNode
}) {
  return (
    <header className="rules-section-heading">
      <div className="rules-section-title">
        <span className="rules-section-icon"><Icon size={20} aria-hidden="true" /></span>
        <div>
          <div className="rules-section-name">
            <h2 id={id}>{title}</h2>
            {count !== undefined && <span className="rules-count">{count}</span>}
          </div>
          <p>{description}</p>
        </div>
      </div>
      {action}
    </header>
  )
}

export function RulesEmptyState({ title, description, children }: {
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="workspace-panel rules-empty">
      <div className="rules-empty-copy">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {children}
    </div>
  )
}

export function RulesLoading({ label }: { label: string }) {
  return <LoadingState label={label} shape="cards" />
}
