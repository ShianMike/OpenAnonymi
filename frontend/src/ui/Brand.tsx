import { Fingerprint } from 'lucide-react'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand${compact ? ' brand--compact' : ''}`}>
      <span className="brand-mark" aria-hidden="true">
        <Fingerprint size={24} strokeWidth={1.6} />
      </span>
      {!compact && (
        <span className="brand-wordmark">
          OpenAnonymi<span className="brand-dot">.</span>
        </span>
      )}
    </span>
  )
}
