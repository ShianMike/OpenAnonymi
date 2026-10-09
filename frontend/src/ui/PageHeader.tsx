import type { ReactNode } from 'react'

type Props = {
  title: string
  titleId?: string
  description?: string
  action?: ReactNode
}

export function PageHeader({ title, titleId, description, action }: Props) {
  return (
    <header className="page-heading">
      <div>
        <h1 id={titleId}>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-heading-action">{action}</div>}
    </header>
  )
}
