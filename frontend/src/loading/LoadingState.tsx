import { cn } from '../ui/cn'
import { LoadingMark } from './LoadingMark'
import { LoadingSkeleton, type LoadingShape } from './LoadingSkeleton'
import { useLoadingAwareness } from './useLoadingAwareness'
import { useLoadingPresence } from './foregroundLoading'
import './loading.css'

export type { LoadingShape } from './LoadingSkeleton'

/** In-page loading. Full-screen loading is LoadingScreen. */
export function LoadingState({ label, description, shape = 'list', compact = false, background = false, className, onRetry, slowMessage }: {
  label: string; description?: string; shape?: LoadingShape; compact?: boolean; background?: boolean; className?: string; onRetry?: () => void; slowMessage?: string
}) {
  const { ref, slow, offline } = useLoadingAwareness()
  useLoadingPresence(ref, !background)
  return <div ref={ref} className={cn('loading-state', !compact && 'loading-state-page', compact && 'loading-state-compact', className)} data-slow={slow} data-offline={offline}>
    <div className={cn('loading-heading', !compact && !slow && !offline && 'sr-only')}>
      <LoadingMark small />
      <div className="loading-copy" role="status" aria-atomic="true">
        <strong>{label}</strong>
        {description && <p className={compact ? 'loading-description' : 'sr-only'}>{description}</p>}
        {(slow || offline) && <span className="loading-wait-note">{offline ? 'You’re offline. Reconnect to continue loading.'
          : slowMessage ?? 'This is taking longer than usual. We’re still waiting for a response.'}</span>}
      </div>
      {(slow || offline) && onRetry && <button type="button" className="loading-retry" onClick={onRetry}>Try again</button>}
    </div>
    {!compact && <LoadingSkeleton shape={shape} />}
  </div>
}
