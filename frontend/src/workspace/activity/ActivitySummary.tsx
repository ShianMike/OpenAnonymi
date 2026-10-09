import { Activity, CalendarDays, ChevronDown, Users } from 'lucide-react'
import * as Popover from '@radix-ui/react-popover'
import type { ActivityView } from '../../api/client'
import { eventName } from '../events'
import { periodLabel } from './activityPresentation'

export function ActivitySummary({ value }: { value: ActivityView }) {
  const counts = Object.entries(value.workspace_counts ?? {}).sort((a, b) => b[1] - a[1])
  const total = counts.reduce((sum, [, count]) => sum + count, 0)
  return <aside className="activity-summary" aria-label="Activity summary">
    <div className="activity-personal-summary">
      <Activity size={19} aria-hidden="true" /><div><span>Your activity</span><strong>{value.own_total.toLocaleString()} <small>events</small></strong></div>
    </div>
    {value.workspace_counts !== null && <div className="activity-workspace-summary">
      <Popover.Root><Popover.Trigger className="activity-summary-trigger"><Users size={19} aria-hidden="true" /><span><span>Across your workspace</span>
        <strong>{total.toLocaleString()} <small>events</small></strong></span><ChevronDown size={15} aria-hidden="true" /></Popover.Trigger>
        <Popover.Portal><Popover.Content className="activity-summary-breakdown" side="bottom" align="end" sideOffset={6} collisionPadding={12} aria-label="Workspace event totals">
          <p>Workspace events · Last 30 days</p>
          <ul>{counts.length ? counts.map(([code, count]) =>
            <li key={code}><span>{eventName(code)}</span><strong>{count.toLocaleString()}</strong></li>) : <li>No workspace events yet.</li>}</ul>
        </Popover.Content></Popover.Portal>
      </Popover.Root>
    </div>}
    <div className="activity-period-summary">
      <CalendarDays size={19} aria-hidden="true" /><div><span>Last 30 days</span><p>{periodLabel(value.since)} — {periodLabel(value.as_of)}</p></div>
    </div>
  </aside>
}
