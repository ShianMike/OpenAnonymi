import { useLoadingMotion } from './useLoadingMotion'

/** Decorative activity indicator; never an estimate of progress. */
export function LoadingMark({ small = false }: { small?: boolean }) {
  const ref = useLoadingMotion<HTMLSpanElement>()
  return <span ref={ref} className={small ? 'loading-mark loading-mark-small' : 'loading-mark'} aria-hidden="true">
    <i /><i /><i />
  </span>
}
