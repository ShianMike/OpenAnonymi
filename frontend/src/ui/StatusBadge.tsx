const labels: Record<string, string> = {
  draft: 'Draft',
  scanning: 'Scanning',
  needs_review: 'Needs review',
  ready: 'Ready',
  exported: 'Exported',
  failed: 'Failed',
  expired: 'Expired',
  deleted: 'Deleted',
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === 'ready' || status === 'exported' ? 'complete'
    : status === 'failed' || status === 'expired' ? 'warning'
      : status === 'needs_review' ? 'attention' : 'neutral'
  return <span className={`status-badge status-badge--${tone}`}>
    {labels[status] ?? status.replaceAll('_', ' ')}
  </span>
}
