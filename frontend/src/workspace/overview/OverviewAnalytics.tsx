import { ChartNoAxesColumn, Clock3, Download, FileCheck2, ScanLine } from 'lucide-react'
import type { OverviewView } from '../../api/client'
import { categoryPresentation } from '../../rules/categoryPresentation'
import { confirmationDuration, exportPercentage } from './analyticsPresentation'
import './analytics.css'

export function OverviewAnalytics({ value }: { value: OverviewView['analytics'] }) {
  return <div className="overview-analytics">
    <section className="overview-progress" aria-labelledby="analytics-heading">
      <div className="overview-card-heading"><div><h2 id="analytics-heading">Your review progress</h2><p>Reviews you created in the last 30 days.</p></div>
        <span className="overview-period">30 days</span>
      </div>
      <dl className="analytics-metrics">
        <div><dt><FileCheck2 size={16} aria-hidden="true" />Active reviews</dt><dd className="analytics-cohort">{value.cohort_documents.toLocaleString()}</dd></div>
        <div><dt><Clock3 size={16} aria-hidden="true" />First confirmation</dt><dd className="analytics-duration">{confirmationDuration(value.average_time_to_confirm_seconds)}</dd></div>
        <div><dt><Download size={16} aria-hidden="true" />Export rate</dt><dd className="analytics-export-rate">{exportPercentage(value.export_rate)}</dd></div>
      </dl>
      {value.cohort_documents === 0 ? <div className="analytics-empty">
        <ChartNoAxesColumn size={18} aria-hidden="true" /><p>Progress begins with your first review.</p>
      </div> : <div className="analytics-export-summary">
        <span>{value.exported_documents.toLocaleString()} of {value.cohort_documents.toLocaleString()} reviews shared</span>
        <span className="analytics-category-track" aria-hidden="true"><span style={{ width: `${(value.export_rate ?? 0) * 100}%` }} /></span>
        <small>{value.confirmed_documents.toLocaleString()} confirmed · {value.average_time_to_confirm_seconds === null ? 'No confirmation time yet' : 'Average time from creation to first confirmation'}</small>
      </div>}
      <details className="analytics-method"><summary>How these numbers work</summary>
        <p>Since {new Date(value.since).toLocaleDateString()}. Deleted and expired reviews are excluded. Assigned reviews belong to their owners’ totals.</p>
        <p>First confirmation is the average time from creation. Repeat confirmations count once per review. Export rate includes reviewed Copy, TXT, Word, CSV and PDF output; redaction reports are excluded.</p>
      </details>
    </section>
    <section className="overview-findings" aria-labelledby="finding-categories-heading">
      <div className="overview-card-heading"><div><h2 id="finding-categories-heading">Finding categories</h2><p>{value.findings_total.toLocaleString()} current findings in recent reviews.</p></div>
        <ScanLine size={19} aria-hidden="true" />
      </div>
      {value.findings_total === 0 ? <div className="analytics-findings-empty">
        <span className="overview-empty-icon"><ScanLine size={27} strokeWidth={1.3} aria-hidden="true" /></span>
        <strong>No findings yet.</strong><p>Scan a draft or add findings to see the breakdown.</p>
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
      <p className="analytics-findings-note">Current source versions only. Removed findings are excluded. Categories describe findings, not people.</p>
    </section>
  </div>
}
