import { PageHeader } from '../ui/PageHeader'
import { LoadingState, type LoadingShape } from './LoadingState'

export function RouteLoading({ pathname, title }: { pathname: string; title: string }) {
  const shape: LoadingShape = pathname.includes('/edit') ? 'document'
    : pathname === '/documents' || pathname === '/rules' ? 'gallery'
    : pathname === '/' ? 'cards' : pathname === '/new' ? 'document'
    : pathname === '/settings' || pathname === '/preferences' ? 'form'
    : pathname === '/members' ? 'members'
    : pathname === '/activity' || pathname.startsWith('/workspaces/') ? 'timeline' : 'list'
  return <section className="route-loading" aria-label={`Opening ${title}`}>
    <PageHeader title={title} />
    <LoadingState label={`Opening ${title.toLowerCase()}…`} shape={shape} />
  </section>
}
