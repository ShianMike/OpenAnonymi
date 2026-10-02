import { PageHeader } from '../ui/PageHeader'
import { LoadingState, type LoadingShape } from './LoadingState'

export function RouteLoading({ pathname, title }: { pathname: string; title: string }) {
  const shape: LoadingShape = pathname.includes('/edit') ? 'document'
    : pathname === '/' || pathname === '/rules' ? 'cards'
    : pathname === '/new' || pathname === '/settings' || pathname === '/preferences' ? 'form' : 'list'
  return <section className="route-loading" aria-label={`Opening ${title}`}>
    <PageHeader title={title} description="Preparing this page…" />
    <LoadingState label={`Opening ${title.toLowerCase()}…`} shape={shape}
      description="Your workspace navigation stays available while the page opens." />
  </section>
}
