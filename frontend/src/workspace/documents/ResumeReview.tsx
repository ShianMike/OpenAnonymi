import { ArrowRight, History } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentIndexView } from '../../api/client'
import { documentLabel } from './documentPresentation'

export function ResumeReview({ item, search }: { item: DocumentIndexView; search: string }) {
  return <div className="document-resume">
    <History size={14} aria-hidden="true" /><span>Last opened</span>
    <Link to={`/documents/${item.id}/edit`} state={{ documentsSearch: search }} aria-label={`Resume ${documentLabel(item)}`}>
      <span>{documentLabel(item)}</span><ArrowRight size={14} aria-hidden="true" />
    </Link>
  </div>
}
