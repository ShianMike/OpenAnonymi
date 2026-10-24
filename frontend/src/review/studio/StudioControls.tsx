import { Children, isValidElement, type ComponentProps, type ReactNode } from 'react'
import * as Select from '@radix-ui/react-select'
import * as Dialog from '@radix-ui/react-dialog'
import { Check, ChevronDown, X } from 'lucide-react'
import './studio.css'

export function StudioSelect({ children, value, onValueChange, ...props }: {
  children: ReactNode; value: string | number; onValueChange: (value: string) => void
} & Omit<ComponentProps<typeof Select.Trigger>, 'children' | 'value' | 'onChange'>) {
  const options = Children.toArray(children).filter(isValidElement<ComponentProps<'option'>>)
  const selected = options.findIndex(option => String(option.props.value) === String(value))
  return <Select.Root value={String(selected)} onValueChange={index => onValueChange(String(options[Number(index)].props.value))} disabled={props.disabled}>
    <Select.Trigger {...props} className={`studio-select ${props.className ?? ''}`}><Select.Value>{options[selected]?.props.children}</Select.Value><Select.Icon><ChevronDown size={14} /></Select.Icon></Select.Trigger>
    <Select.Portal><Select.Content className="studio studio-select-menu" position="popper" sideOffset={5} collisionPadding={10}>
      <Select.Viewport>{options.map((option, index) => <Select.Item key={index} value={String(index)} disabled={option.props.disabled} className="studio-select-option">
        <Select.ItemText>{option.props.children}</Select.ItemText><Select.ItemIndicator><Check size={15} /></Select.ItemIndicator>
      </Select.Item>)}</Select.Viewport>
    </Select.Content></Select.Portal>
  </Select.Root>
}

export function StudioDialog({ title, description, children, className = '', busy = false, onCloseAutoFocus, onOpenAutoFocus }: {
  title: string; description: string; children: ReactNode; className?: string; busy?: boolean; onCloseAutoFocus?: ComponentProps<typeof Dialog.Content>['onCloseAutoFocus']; onOpenAutoFocus?: ComponentProps<typeof Dialog.Content>['onOpenAutoFocus']
}) {
  return <Dialog.Portal><Dialog.Overlay className="studio-overlay" />
    <Dialog.Content className={`studio studio-dialog ${className}`} onEscapeKeyDown={event => { if (busy) event.preventDefault() }}
      onPointerDownOutside={event => { if (busy) event.preventDefault() }} onCloseAutoFocus={onCloseAutoFocus} onOpenAutoFocus={onOpenAutoFocus}>
      <header className="studio-dialog-heading"><div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description></div>
        <Dialog.Close className="studio-icon" disabled={busy} aria-label={`Close ${title.toLowerCase()}`}><X size={18} /></Dialog.Close>
      </header>{children}
    </Dialog.Content>
  </Dialog.Portal>
}
