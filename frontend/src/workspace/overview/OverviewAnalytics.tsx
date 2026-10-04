import { Clock3, Download, FileCheck2 } from 'lucide-react'
import type { OverviewView } from '../../api/client'
import { categoryPresentation } from '../../rules/categoryPresentation'
import { confirmationDuration, exportPercentage } from './analyticsPresentation'
import './analytics.css'

export function OverviewAnalytics({ value, refresh }: {
  value: OverviewView['analytics']; refresh: () => void
}) {
  return <section className="surface-panel overview-analytics" aria-labelledby="analytics-heading">
    <div className="section-heading">
      <div>
        <h2 id="analytics-heading">Your review progress</h2>
        <p>Your active reviews created in this workspace in the last 30 days.</p>
      </div>
      <button type="button" onClick={refresh}>Refresh overview</button>
    </div>
    <p className="analytics-scope">Since {new Date(value.since).toLocaleDateString()}. Deleted and expired reviews are excluded. Assigned reviews belong to their owners’ totals.</p>
    <div className="overview-metrics analytics-metrics">
      <article className="metric-card">
        <span><FileCheck2 size={17} aria-hidden="true" /> Active reviews</span>
        <strong className="analytics-cohort">{value.cohort_documents.toLocaleString()}</strong>
        <small>The denominator for export rate</small>
      </article>
      <article className="metric-card">
        <span><Clock3 size={17} aria-hidden="true" /> Time to first confirmation</span>
        <strong className="analytics-duration">{confirmationDuration(value.average_time_to_confirm_seconds)}</strong>
        <small>{value.confirmed_documents === 0 ? 'No confirmations in this group yet' : `Average across ${value.confirmed_documents.toLocaleString()} confirmed reviews, from creation`}</small>
      </article>
      <article className="metric-card">
        <span><Download size={17} aria-hidden="true" /> Export rate</span>
        <strong className="analytics-export-rate">{exportPercentage(value.export_rate)}</strong>
        <small>{value.exported_documents.toLocaleString()} of {value.cohort_documents.toLocaleString()} reviews exported or copied at least once</small>
      </article>
    </div>
    <p className="analytics-detail">Repeat confirmations count once per review. Export rate includes reviewed Copy, TXT, Word, CSV and PDF output; redaction reports are excluded.</p>
    <div className="analytics-category-heading">
      <h3>Finding categories</h3>
      <span>{value.findings_total.toLocaleString()} current findings</span>
    </div>
    <p className="analytics-detail">Current source versions in the same group of reviews. Removed findings are excluded; categories describe findings, not people.</p>
    {value.findings_total === 0 ? <div className="empty-state analytics-empty">
      <strong>No current findings in this group</strong>
      <p>Saved findings appear here after you scan or add them to a review.</p>
    </div> : <ul className="analytics-categories">
      {value.categories.map(({ category, count }) => {
        const { label, icon: Icon } = categoryPresentation[category]
        const share = count / value.findings_total
        return <li key={category}>
          <div className="analytics-category-label"><Icon size={17} aria-hidden="true" /><span>{label}</span></div>
          <strong>{count.toLocaleString()} <small>{exportPercentage(share)}</small></strong>
          <span className="analytics-category-track" aria-hidden="true"><span style={{ width: `${share * 100}%` }} /></span>
        </li>
      })}
    </ul>}
  </section>
}
