import { cn } from '../ui/cn'
import { Brand } from '../ui/Brand'
import { LoadingMark } from './LoadingMark'
import { useLoadingAwareness } from './useLoadingAwareness'
import { useLoadingPresence } from './foregroundLoading'
import './loading.css'

export type LoadingShape = 'list' | 'cards' | 'document' | 'form'

function Skeleton({ shape }: { shape: LoadingShape }) {
  return <div className={cn('loading-skeleton', `loading-skeleton-${shape}`)} aria-hidden="true" inert>
    {[0, 1, 2].map(index => <div className="loading-placeholder" key={index}>
      <span className="loading-placeholder-symbol" />
      <div><i /><i /><i /></div>
      <span className="loading-placeholder-tag" />
    </div>)}
  </div>
}

export function LoadingState({ label, description, shape = 'list', compact = false, className, onRetry, slowMessage, heading = false }: {
  label: string; description?: string; shape?: LoadingShape; compact?: boolean; className?: string; onRetry?: () => void; slowMessage?: string; heading?: boolean
}) {
  const { ref, slow, offline } = useLoadingAwareness()
  useLoadingPresence(ref, !compact)
  const Title = heading ? 'h1' : 'strong'
  return <div ref={ref} className={cn('loading-state', compact && 'loading-state-compact', className)} data-slow={slow} data-offline={offline}>
    <div className="loading-heading">
      {heading ? <span className="loading-mark loading-mark-entrance" aria-hidden="true"><Brand compact /></span>
        : <LoadingMark small={compact} />}
      <div className="loading-copy" role="status" aria-atomic="true">
        <Title>{label}</Title>
        {description && !compact && <p>{description}</p>}
        <span className="loading-wait-note">{offline ? 'You appear to be offline. Waiting for a connection.'
          : slow ? slowMessage ?? 'Taking longer than usual. Still waiting for a response.' : 'Please wait a moment.'}</span>
      </div>
    </div>
    {!compact && !heading && <Skeleton shape={shape} />}
    {(slow || offline) && onRetry && <button type="button" className="loading-retry" onClick={onRetry}>Try again</button>}
  </div>
}
