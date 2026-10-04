export function confirmationDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 1) return '<1 sec'
  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
  if (seconds < 60) return `${number.format(seconds)} sec`
  if (seconds < 3600) return `${number.format(seconds / 60)} min`
  if (seconds < 86400) return `${number.format(seconds / 3600)} hr`
  return `${number.format(seconds / 86400)} days`
}

export function exportPercentage(rate: number | null): string {
  return rate === null ? '—' : new Intl.NumberFormat(undefined, {
    style: 'percent', maximumFractionDigits: 1,
  }).format(rate)
}
