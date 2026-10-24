import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowUpRight, Bell, CheckCheck, CircleAlert, RefreshCw, Settings2 } from 'lucide-react'
import type { SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { DialogFrame } from '../ui/WorkspaceControls'
import { NotificationList } from './NotificationList'
import { NotificationPreview } from './NotificationPreview'
import { NotificationPreferencesPanel } from './NotificationPreferencesPanel'
import { useNotifications } from './useNotifications'
import './notifications.css'

const VISIBLE_BATCH = 20

export function NotificationsPage({ session }: { session: SessionView }) {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'unread' ? 'unread' : 'all'
  const [limit, setLimit] = useState(VISIBLE_BATCH)
  const activeTab = useRef<HTMLButtonElement>(null)
  const previewTrigger = useRef<HTMLButtonElement | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [acknowledged, setAcknowledged] = useState<string | null>(null)
  const { data, pending, notice, actionError, read, loadOlder, refresh } = useNotifications(session)
  const ready = data.kind === 'ready' ? data : null
  const visible = ready?.page.items.filter(item => view === 'all' || !item.read_at) ?? []
  const more = visible.length > limit || !!ready?.page.next_cursor && (view === 'all' || !!ready.unread)
  function changeView(next: string) {
    setLimit(VISIBLE_BATCH)
    setParams(current => { const search = new URLSearchParams(current); if (next === 'unread') search.set('view', next); else search.delete('view'); return search }, { replace: true })
  }
  async function acknowledge(id?: string) {
    if (await read(id)) activeTab.current?.focus()
  }
  async function showOlder() {
    if (visible.length <= limit) await loadOlder()
    setLimit(current => current + VISIBLE_BATCH)
  }
  return <section className="notifications-page" aria-labelledby="notifications-title">
    <header className="notification-heading">
      <div><h1 id="notifications-title">Notifications</h1><p>Assignments, approvals and comments, in one inbox.</p></div>
      <Dialog.Root>
        <Dialog.Trigger className="notification-settings"><Settings2 size={15} aria-hidden="true" /><span>Preferences</span></Dialog.Trigger>
        <DialogFrame className="notification-preferences-dialog" title="Notification preferences" description="Choose how review updates reach you.">
          <NotificationPreferencesPanel key={session.user_id} session={session} />
        </DialogFrame>
      </Dialog.Root>
    </header>
    <Tabs.Root value={view} onValueChange={changeView}>
      <div className="notification-toolbar">
        <Tabs.List className="notification-views" aria-label="Notification views">
          <Tabs.Trigger value="all" ref={view === 'all' ? activeTab : undefined}>All</Tabs.Trigger>
          <Tabs.Trigger value="unread" ref={view === 'unread' ? activeTab : undefined}>Unread{ready && <span>{ready.unread}</span>}</Tabs.Trigger>
        </Tabs.List>
        <div className="notification-inbox-tools">
          <button type="button" className="notification-mark-all" disabled={!!pending || !ready?.unread} onClick={() => void acknowledge()}><CheckCheck size={15} aria-hidden="true" /><span>{pending === 'all' ? 'Saving…' : 'Mark all read'}</span></button>
          <button type="button" className="notification-refresh" aria-label="Refresh notifications" title="Refresh notifications" disabled={!!pending || data.kind === 'loading'} onClick={() => { setLimit(VISIBLE_BATCH); refresh() }}><RefreshCw size={15} aria-hidden="true" /></button>
        </div>
      </div>
      <Tabs.Content value={view} className="notification-feed">
        <div className="notification-feed-meta"><span role="status">{notice || 'Newest first'}</span>{ready && view === 'unread' && ready.unread > 0 && <span>Unread updates</span>}</div>
        {data.kind === 'loading' && <LoadingState label="Checking your inbox…" description="Loading updates you can access." shape="list" onRetry={refresh} />}
        {data.kind === 'error' && <div className="notification-error" role="alert"><CircleAlert size={24} strokeWidth={1.5} aria-hidden="true" /><h2>Inbox couldn’t be loaded</h2><p>{data.message}</p><button type="button" onClick={refresh}>Try again</button></div>}
        {ready && <>
          {visible.length ? <NotificationList items={visible.slice(0, limit)} pending={pending} onRead={id => void acknowledge(id)} now={ready.checkedAt}
            onOpen={(id, trigger) => { previewTrigger.current = trigger; setSelected(id) }} />
            : <div className="notification-empty">
              {view === 'unread' ? <CheckCheck size={30} strokeWidth={1.3} aria-hidden="true" /> : <Bell size={30} strokeWidth={1.3} aria-hidden="true" />}
              <h2>{view === 'unread' ? ready.unread && ready.page.next_cursor ? 'Your unread updates are further back' : 'You’re all caught up' : 'A quiet inbox'}</h2>
              <p>{view === 'unread' ? ready.unread && ready.page.next_cursor ? 'Load older updates to find the notifications you haven’t read yet.' : 'There’s nothing new to check. You can still browse your earlier updates.' : 'When someone assigns a review, requests approval, or leaves a comment, you’ll find it here.'}</p>
              {view === 'unread' ? <button type="button" onClick={() => changeView('all')}>View all updates</button>
                : <Link to="/documents">Browse documents<ArrowUpRight size={14} aria-hidden="true" /></Link>}
            </div>}
          {actionError && <p className="notification-action-error" role="alert">{actionError}</p>}
          {more && <div className="notification-load-older"><button type="button" disabled={!!pending} onClick={() => void showOlder()}><ArrowDown size={14} aria-hidden="true" />{pending === 'more' ? 'Loading updates…' : actionError ? 'Try loading again' : 'Load older updates'}</button></div>}
        </>}
      </Tabs.Content>
    </Tabs.Root>
    <Dialog.Root open={selected !== null && data.kind !== 'error'} onOpenChange={open => { if (!open) setSelected(null) }}>
      {selected && data.kind !== 'error' && <NotificationPreview key={`${session.user_id}:${session.csrf_token}:${selected}`} id={selected}
        read={acknowledged === selected || !!ready?.page.items.find(item => item.id === selected)?.read_at} pending={!!pending}
        onViewed={item => { if (!item.read_at) void read(item.id).then(saved => { if (saved) setAcknowledged(item.id) }) }} onNavigate={() => setSelected(null)}
        onCloseAutoFocus={event => { event.preventDefault(); (previewTrigger.current?.isConnected ? previewTrigger.current : activeTab.current)?.focus() }} />}
    </Dialog.Root>
    <p className="notification-retention">Updates are kept for 30 days. Review access is checked before details are shown.</p>
  </section>
}
