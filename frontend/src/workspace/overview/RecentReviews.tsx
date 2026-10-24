import { useEffect, useState } from 'react'
import { ArrowRight, FileText, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getWorkspaceDocuments, type DocumentIndexView } from '../../api/client'
import { StatusBadge } from '../../ui/StatusBadge'
import { documentLabel, relativeEdit } from '../documents/documentPresentation'
import { recentAvailableReviews } from './overviewPresentation'
import { LoadingState } from '../../loading/LoadingState'

type Data = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready'; items: DocumentIndexView[] }

export function RecentReviews({ workspaceId }: { workspaceId: string }) {
  const [data, setData] = useState<Data>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    getWorkspaceDocuments(workspaceId, controller.signal).then(items => {
      if (!controller.signal.aborted) { setData({ kind: 'ready', items }); setNow(Date.now()) }
    }).catch(() => { if (!controller.signal.aborted) setData({ kind: 'error' }) })
    return () => controller.abort()
  }, [workspaceId, attempt])
  const query = `?workspace=${encodeURIComponent(workspaceId)}`
  const items = data.kind === 'ready' ? recentAvailableReviews(data.items, now) : []

  return <section className="overview-recent" aria-labelledby="recent-reviews-heading">
    <header className="overview-card-heading">
      <div><h2 id="recent-reviews-heading">Recent reviews</h2><p>Your latest available reviews, including those shared with you.</p></div>
      <Link to={`/documents${query}`} className="overview-text-link">View all <ArrowRight size={14} aria-hidden="true" /></Link>
    </header>
    {data.kind === 'loading' && <LoadingState className="overview-recent-loading" label="Loading recent reviews…" shape="list" onRetry={() => setAttempt(value => value + 1)} />}
    {data.kind === 'error' && <div className="overview-recent-message" role="alert"><p>We couldn’t load your recent reviews.</p><button type="button" onClick={() => { setData({ kind: 'loading' }); setAttempt(value => value + 1) }}>Try again</button></div>}
    {data.kind === 'ready' && (items.length === 0 ? <div className="overview-recent-empty">
      <FileText size={28} strokeWidth={1.3} aria-hidden="true" />
      <h3>No available reviews</h3>
      <p>Start with a draft. Review the personal details, then choose what to share.</p>
      <Link to={`/new${query}`} className="overview-secondary-action"><Plus size={15} aria-hidden="true" /> Create a review</Link>
    </div> : <div className="overview-recent-table"><table aria-label="Recent available reviews">
      <thead><tr><th scope="col">Document</th><th scope="col">Status</th><th scope="col">Updated</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.id}>
        <th scope="row"><div className="overview-document-name"><FileText size={19} strokeWidth={1.5} aria-hidden="true" /><div>
          <Link to={`/documents/${encodeURIComponent(item.id)}/edit`}>{documentLabel(item)}</Link>
          {!item.is_owner && <small>Shared with you</small>}
        </div></div></th>
        <td><StatusBadge status={item.status} /></td>
        <td><time dateTime={item.updated_at} title={new Date(item.updated_at).toLocaleString()}>{relativeEdit(item.updated_at, now)}</time></td>
      </tr>)}</tbody>
    </table></div>)}
    <footer className="overview-recent-footer"><span>Looking for an older review?</span><Link className="overview-text-link" to={`/documents${query}`}>Open documents <ArrowRight size={14} aria-hidden="true" /></Link></footer>
  </section>
}
