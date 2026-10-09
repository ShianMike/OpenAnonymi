import { BookOpen } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { BranchCurve } from '../shell/BranchCurve'
import { workspaceHref } from '../shell/navigation'
import './resume.css'

export function ResumeReviewLink({ onClick, workspaceId }: { onClick: () => void; workspaceId?: string }) {
  return (
    <NavLink
      className={({ isActive }) => `branch-link resume-review-link${isActive ? ' is-active' : ''}`}
      to={workspaceHref('/continue', workspaceId)}
      onClick={onClick}
    >
      {({ isActive }) => <>
        <BranchCurve />
        <BookOpen size={16} strokeWidth={1.5} aria-hidden="true" />
        <span>Continue review</span>
        {isActive && <span className="branch-active-dot" aria-hidden="true" />}
      </>}
    </NavLink>
  )
}
