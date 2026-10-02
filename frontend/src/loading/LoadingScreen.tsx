import { LoadingState, type LoadingShape } from './LoadingState'
import { EntranceFrame } from './EntranceFrame'

export function LoadingScreen({ label, description, shape = 'document' }: {
  label: string; description: string; shape?: LoadingShape
}) {
  return <EntranceFrame>
    <LoadingState label={label} description={description} shape={shape} heading onRetry={() => window.location.reload()} />
  </EntranceFrame>
}
