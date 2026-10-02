import { BookOpen } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { BranchCurve } from '../shell/BranchCurve'
import './resume.css'

export function ResumeReviewLink({ onClick }: { onClick: () => void }) {
  return (
    <NavLink
      className={({ isActive }) => `branch-link resume-review-link${isActive ? ' is-active' : ''}`}
      to="/continue"
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
