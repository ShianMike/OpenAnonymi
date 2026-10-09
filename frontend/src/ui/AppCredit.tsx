import * as Menu from '@radix-ui/react-dropdown-menu'
import { ChevronDown } from 'lucide-react'
import './app-credit.css'

const source = 'https://github.com/ShianMike/OpenAnonymi'

export function AppCredit() {
  return <div className="app-credit">
    <span className="app-credit-attribution">Powered by OpenAnonymi <span>© 2026 ShianMike</span></span>
    <Menu.Root modal={false}>
      <Menu.Trigger className="app-credit-trigger">Legal & support <ChevronDown size={13} aria-hidden="true" /></Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className="app-credit-menu" side="top" align="end" sideOffset={8} collisionPadding={16}>
          <Menu.Item asChild><a href="/terms" target="_blank" rel="noopener noreferrer" aria-label="Terms of Service (opens in a new tab)">Terms of Service</a></Menu.Item>
          <Menu.Item asChild><a href="/privacy" target="_blank" rel="noopener noreferrer" aria-label="Privacy Notice (opens in a new tab)">Privacy Notice</a></Menu.Item>
          <Menu.Item asChild><a href="mailto:support@openanonymi.com">Contact support</a></Menu.Item>
          <Menu.Separator className="app-credit-separator" />
          <Menu.Item asChild><a href={`${source}/blob/main/NOTICE`} target="_blank" rel="noopener noreferrer">License & notices</a></Menu.Item>
          <Menu.Item asChild><a href={source} target="_blank" rel="noopener noreferrer">Source code</a></Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  </div>
}
