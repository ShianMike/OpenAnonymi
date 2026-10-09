import { LoadingState } from './LoadingState'
import { EntranceFrame } from './EntranceFrame'

export function LoadingScreen({ label, description }: {
  label: string; description: string
}) {
  return <EntranceFrame>
    <LoadingState label={label} description={description} heading onRetry={() => window.location.reload()} />
  </EntranceFrame>
}
