import type { FindingCategory } from '../api/client'
import { categoryPresentation } from './categoryPresentation'
import './category-badge.css'

export function CategoryBadge({ category }: { category: FindingCategory }) {
  const { label, icon: Icon } = categoryPresentation[category]
  return <span className="finding-kind category-kind" data-category={category}>
    <Icon size={12} aria-hidden="true" /><span>{label}</span>
  </span>
}
