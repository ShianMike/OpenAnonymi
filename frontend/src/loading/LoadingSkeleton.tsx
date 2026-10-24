export type LoadingShape = 'list' | 'gallery' | 'cards' | 'document' | 'page' | 'form' | 'timeline' | 'members' | 'comparison'

function Lines() {
  return <span className="skeleton-lines"><i /><i /></span>
}

function Page() {
  return <div className="skeleton-paper"><span className="skeleton-paper-heading"><i /><i /></span>
    {[0, 1, 2].map(index => <div className="skeleton-paragraph" key={index}><i /><i /><i /><i /></div>)}
  </div>
}

function Rows({ shape }: { shape: 'list' | 'timeline' | 'members' }) {
  return <>{[0, 1, 2, 3].map(index => <div className="skeleton-row" key={index}>
    {shape === 'members' && <i className="skeleton-avatar" />}
    {shape === 'timeline' && <i className="skeleton-time" />}
    <Lines /><i className="skeleton-meta" />
  </div>)}</>
}

export function LoadingSkeleton({ shape }: { shape: LoadingShape }) {
  let content
  switch (shape) {
    case 'gallery':
      content = <>{[0, 1, 2, 3, 4, 5].map(index => <div className="skeleton-card" key={index}>
        <Lines /><div className="skeleton-card-summary"><i /><i /></div>
        <div className="skeleton-card-footer"><i /><i /></div>
      </div>)}</>
      break
    case 'cards':
      content = <><div className="skeleton-metrics">{[0, 1, 2, 3].map(index => <div className="skeleton-metric" key={index}><i /><i /><i /></div>)}</div>
        <div className="skeleton-overview-work"><div className="skeleton-panel"><Lines /><Rows shape="list" /></div>
          <div className="skeleton-panel"><Lines /><div className="skeleton-summary"><i /><i /><i /><i /></div></div></div>
      </>
      break
    case 'document':
      content = <><div className="skeleton-editor"><div className="skeleton-editor-bar"><i /><i /></div><Page /></div>
        <div className="skeleton-inspector"><Lines /><div className="skeleton-inspector-summary"><i /><i /></div><Rows shape="list" /></div></>
      break
    case 'page':
      content = <Page />
      break
    case 'comparison':
      content = <><Page /><Page /></>
      break
    case 'form':
      content = <><Lines />{[0, 1, 2].map(index => <div className="skeleton-setting" key={index}><Lines /><i className="skeleton-setting-value" /></div>)}</>
      break
    default:
      content = <Rows shape={shape} />
  }
  return <div className={`loading-skeleton loading-skeleton-${shape}`} aria-hidden="true" inert>{content}</div>
}
