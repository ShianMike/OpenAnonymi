import { Activity, ShieldCheck, Users } from 'lucide-react'
import type { ActivityView } from '../../api/client'
import { eventName } from '../events'
import { periodLabel } from './activityPresentation'

export function ActivitySummary({ value }: { value: ActivityView }) {
  const counts = Object.entries(value.workspace_counts ?? {}).sort((a, b) => b[1] - a[1])
  const total = counts.reduce((sum, [, count]) => sum + count, 0)
  const maximum = Math.max(...counts.map(([, count]) => count), 1)
  return (
    <aside className="activity-summary" aria-label="Activity summary">
      <div className="activity-personal-summary workspace-panel">
        <span className="activity-summary-label">
          <Activity size={15} aria-hidden="true" /> Your activity
        </span>
        <strong className="activity-big-number">
          {value.own_total.toLocaleString()}
          <span>events</span>
        </strong>
        <p>
          {periodLabel(value.since)} — {periodLabel(value.as_of)}
        </p>
      </div>
      {value.workspace_counts !== null && (
        <div className="activity-workspace-summary workspace-panel">
          <h2>
            <Users size={17} aria-hidden="true" /> Across your workspace
          </h2>
          <p>{total.toLocaleString()} events · All members, same period</p>
          {counts.length ? (
            <ul>
              {counts.map(([code, count]) => (
                <li key={code}>
                  <div>
                    <span>{eventName(code)}</span>
                    <strong>{count.toLocaleString()}</strong>
                  </div>
                  <span className="activity-count-track" aria-hidden="true">
                    <i style={{ width: `${(count / maximum) * 100}%` }} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No workspace events yet.</p>
          )}
        </div>
      )}
      <div className="activity-privacy">
        <ShieldCheck size={18} strokeWidth={1.5} aria-hidden="true" />
        <div>
          <strong>A record of actions.</strong>
          <p>
            Activity stores event details, never document text. Review titles are shown from your document
            list.
          </p>
        </div>
      </div>
    </aside>
  )
}
