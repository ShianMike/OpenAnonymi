import { useRef } from 'react'
import { Link } from 'react-router-dom'
import * as Menu from '@radix-ui/react-dropdown-menu'
import { ArrowUpRight, History, MoreHorizontal, Trash2 } from 'lucide-react'
import type { DocumentIndexView } from '../../api/client'
import { documentLabel } from './documentPresentation'

export function DocumentActions({
  item,
  workspaceId,
  unavailable,
  onDelete,
}: {
  item: DocumentIndexView
  workspaceId: string
  unavailable: boolean
  onDelete: (item: DocumentIndexView, trigger: HTMLButtonElement | null) => void
}) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const openingDialogRef = useRef(false)
  const title = documentLabel(item)
  return (
    <div className="document-actions">
      {!unavailable && (
        <Link
          className="document-open"
          to={`/documents/${item.id}/edit`}
          aria-label={`Open review: ${title}`}
          title="Open review"
        >
          <ArrowUpRight size={18} aria-hidden="true" />
        </Link>
      )}
      <Menu.Root modal={false}>
        <Menu.Trigger
          ref={triggerRef}
          className="document-more"
          aria-label={`Actions for ${title}`}
          title="More actions"
        >
          <MoreHorizontal size={19} aria-hidden="true" />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content
            className="document-action-menu"
            align="end"
            sideOffset={7}
            collisionPadding={12}
            onCloseAutoFocus={(event) => {
              if (openingDialogRef.current) {
                event.preventDefault()
                openingDialogRef.current = false
              }
            }}
          >
            <Menu.Label className="document-menu-label">Document actions</Menu.Label>
            <Menu.Item asChild>
              <Link to={`/workspaces/${workspaceId}/documents/${item.id}/history`}>
                <History size={16} aria-hidden="true" /> Review history
              </Link>
            </Menu.Item>
            <Menu.Separator className="document-menu-separator" />
            <Menu.Item
              className="document-menu-delete"
              disabled={!item.is_owner}
              onSelect={() => {
                openingDialogRef.current = true
                onDelete(item, triggerRef.current)
              }}
            >
              <Trash2 size={16} aria-hidden="true" /> Delete review
            </Menu.Item>
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
    </div>
  )
}
