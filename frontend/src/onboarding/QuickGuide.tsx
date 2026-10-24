import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, FileUp, LockKeyhole, X } from 'lucide-react'
import { DialogFrame } from '../ui/WorkspaceControls'
import { cn } from '../ui/cn'
import { hasSeenGuide, rememberGuide } from './guideSeen'
import './quick-guide.css'

const GuideContext = createContext<(() => void) | null>(null)
const topics = [
  { id: 'document', label: 'Add a document' },
  { id: 'settings', label: 'Choose settings' },
  { id: 'decisions', label: 'Review findings' },
  { id: 'export', label: 'Confirm & export' },
] as const
type Topic = typeof topics[number]['id']
type Decision = 'replace' | 'hide' | 'keep'

export function QuickGuideProvider({ userId, offer = true, children }: {
  userId: string; offer?: boolean; children: ReactNode
}) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [offered, setOffered] = useState(() => !hasSeenGuide(userId))
  const [initialTopic, setInitialTopic] = useState<Topic>('document')
  const returnFocus = useRef<HTMLElement | null>(null)
  const dismissOffer = () => { rememberGuide(userId); setOffered(false) }
  const skipGuide = () => { dismissOffer(); document.getElementById('main-content')?.focus({ preventScroll: true }) }
  const openGuide = () => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setInitialTopic(/^\/documents\/[^/]+\/edit$/.test(pathname) ? 'decisions' : 'document')
    dismissOffer()
    setOpen(true)
  }
  useEffect(() => {
    const changed = () => { if (hasSeenGuide(userId)) setOffered(false) }
    window.addEventListener('storage', changed)
    return () => window.removeEventListener('storage', changed)
  }, [userId])
  const showOffer = offered && offer && ['/', '/documents', '/new'].includes(pathname)
  return <GuideContext.Provider value={openGuide}>
    {children}
    {showOffer && <aside className={cn('guide-welcome', pathname === '/new' && 'guide-welcome-in-editor')} aria-labelledby="guide-welcome-title">
      <button type="button" className="guide-welcome-close" aria-label="Dismiss quick guide introduction" onClick={skipGuide}><X size={16} aria-hidden="true" /></button>
      <span className="guide-eyebrow"><BookOpen size={15} aria-hidden="true" /> A little help to get started</span>
      <h2 id="guide-welcome-title">Your first review, step by step.</h2>
      <p>Learn what to check, how decisions work, and what leaves your workspace.</p>
      <div className="guide-welcome-actions"><button type="button" className="guide-primary" aria-haspopup="dialog" onClick={openGuide}>Show me around <ArrowRight size={15} aria-hidden="true" /></button><button type="button" onClick={skipGuide}>Not now</button></div>
      <small>You can reopen this from Quick guide anytime.</small>
    </aside>}
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <DialogFrame className="quick-guide-dialog" title="Quick guide" description="Four steps from your original document to a reviewed version."
        onCloseAutoFocus={event => {
          event.preventDefault()
          const target = returnFocus.current
          if (target?.isConnected && target.getClientRects().length && !target.closest('[inert]')) target.focus({ preventScroll: true })
          else if (target?.closest('#app-sidebar')) document.querySelector<HTMLElement>('[aria-controls="app-sidebar"]')?.focus({ preventScroll: true })
          else document.getElementById('main-content')?.focus({ preventScroll: true })
        }}>
        <QuickGuideSteps initialTopic={initialTopic} onDone={() => setOpen(false)} />
      </DialogFrame>
    </Dialog.Root>
  </GuideContext.Provider>
}

export function QuickGuideButton({ className, onClick }: { className?: string; onClick?: () => void }) {
  const openGuide = useContext(GuideContext)
  if (!openGuide) return null
  return <button type="button" className={cn('quick-guide-trigger', className)} aria-label="Quick guide" title="Quick guide" aria-haspopup="dialog" onClick={() => { openGuide(); onClick?.() }}>
    <BookOpen size={16} strokeWidth={1.7} aria-hidden="true" /><span>Quick guide</span>
  </button>
}

export function DecisionExample({ decision, onChange }: { decision: Decision | null; onChange: (decision: Decision) => void }) {
  return <figure className="guide-example guide-decision-example">
    <figcaption>Try it with a fictional detail <span>Practice only</span></figcaption>
    <p className="guide-source-line">Send the notes to <mark>alex@example.test</mark>.</p>
    <div className="guide-decisions" role="group" aria-label="Try a review decision">
      {(['replace', 'hide', 'keep'] as const).map(value => <button key={value} type="button" aria-pressed={decision === value} onClick={() => onChange(value)}>{value === 'replace' ? 'Replace' : value === 'hide' ? 'Hide' : 'Keep'}</button>)}
    </div>
    <div className="guide-example-result" role="status" aria-live="polite" aria-atomic="true">
      <span>Reviewed output</span>
      <p>{decision ? <>Send the notes to <strong>{decision === 'replace' ? 'EMAIL_001' : decision === 'hide' ? '[REDACTED]' : 'alex@example.test'}</strong>.</> : 'Choose an action to see what changes.'}</p>
      <small>{decision === 'replace' ? 'A category label replaces this email address.' : decision === 'hide' ? 'The detail is covered with a redaction marker.' : decision === 'keep' ? 'The email stays visible. In a real review, Keep requires a reason.' : 'This example never changes your documents.'}</small>
    </div>
  </figure>
}

export function QuickGuideSteps({ initialTopic = 'document', onDone }: { initialTopic?: Topic; onDone: () => void }) {
  const [topic, setTopic] = useState<Topic>(initialTopic)
  const [decision, setDecision] = useState<Decision | null>(null)
  const step = topics.findIndex(item => item.id === topic)
  return <>
    <Tabs.Root className="guide-topics" value={topic} onValueChange={value => setTopic(value as Topic)}>
      <Tabs.List className="guide-topic-list" aria-label="Quick guide steps">
        {topics.map((item, index) => <Tabs.Trigger key={item.id} value={item.id}><span className="guide-step-number" aria-hidden="true">{index + 1}</span><span>{item.label}</span></Tabs.Trigger>)}
      </Tabs.List>
      <div className="guide-body" key={topic}>
        <Tabs.Content value="document" className="guide-panel">
          <div className="guide-copy"><span className="guide-eyebrow">01 / Your starting point</span><h3>Bring in the version you want to share.</h3><p>Choose <strong>New review</strong>, then paste text or upload one file. Give it a title so you can find it again.</p><ul><li>Use PDF for a document’s page layout.</li><li>Check extracted text for anything missing or misread.</li><li>Use <strong>Save as draft</strong> if you want to return later.</li></ul></div>
          <figure className="guide-example guide-document-example"><figcaption><FileUp size={16} aria-hidden="true" /> Example document</figcaption><div className="guide-paper"><span>INTERVIEW NOTES</span><h4>A simpler way to get started</h4><p>The participant asked for clearer account settings and a shorter setup.</p><p>Send the notes to alex@example.test.</p></div><div className="guide-file-types">TXT · Markdown · PDF · Word · Images</div></figure>
          <p className="guide-note"><LockKeyhole size={15} aria-hidden="true" /> Files are processed by OpenAnonymi. Your original stays intact until its retention period ends.</p>
        </Tabs.Content>
        <Tabs.Content value="settings" className="guide-panel">
          <div className="guide-copy"><span className="guide-eyebrow">02 / Before you scan</span><h3>Choose what this review should check.</h3><p>In <strong>Review settings</strong>, choose a coverage preset or customize the categories. Unchecked categories won’t be scanned.</p><ul><li>Set the region for local phone numbers and dates.</li><li>Choose how long the review’s content stays available.</li><li>Select <strong>Start review</strong> to find suggestions.</li></ul></div>
          <figure className="guide-example guide-settings-example"><figcaption>Example settings <span>For illustration</span></figcaption><dl><div><dt>Coverage</dt><dd>Contact details<small>Email addresses & phone numbers</small></dd></div><div><dt>Phone region</dt><dd>United States</dd></div><div><dt>Keep this review for</dt><dd>7 days<small>Content becomes unavailable after expiry</small></dd></div></dl></figure>
          <p className="guide-note"><BookOpen size={15} aria-hidden="true" /> Presets are a starting point. The full text still needs your review.</p>
        </Tabs.Content>
        <Tabs.Content value="decisions" className="guide-panel">
          <div className="guide-copy"><span className="guide-eyebrow">03 / Your decisions</span><h3>A suggestion is yours to decide.</h3><p>Select a highlighted detail or choose it in <strong>Findings</strong>. Replace it, hide it, or keep it with a reason.</p><ul><li><strong>Replace</strong> can use a category label or another available style.</li><li><strong>Hide</strong> removes the detail from the reviewed output.</li><li><strong>Keep</strong> leaves it visible to anyone you share with.</li></ul></div>
          <DecisionExample decision={decision} onChange={setDecision} />
          <p className="guide-note"><ChevronRight size={15} aria-hidden="true" /> Suggestions can miss details. Use <strong>Edit text</strong> (or <strong>Mark text</strong> for a PDF) to add one yourself.</p>
        </Tabs.Content>
        <Tabs.Content value="export" className="guide-panel">
          <div className="guide-copy"><span className="guide-eyebrow">04 / Your final check</span><h3>Read the whole output before it leaves.</h3><p>Open <strong>Output</strong> and check the full document. Choose <strong>Review & export</strong> to confirm it, or <strong>Export</strong> if it’s already confirmed.</p><ul><li>Choose a file format and select <strong>Prepare download</strong>.</li><li>Use the <strong>Save</strong> link to download the prepared file.</li><li>Or choose <strong>Copy reviewed text</strong> after confirmation.</li></ul></div>
          <figure className="guide-example guide-export-example"><figcaption>The version you share <span>Example</span></figcaption><div className="guide-paper"><span>REVIEWED OUTPUT</span><p>Send the notes to <strong>EMAIL_001</strong>.</p><p>The participant asked for clearer account settings and a shorter setup.</p></div><div className="guide-export-caption"><Check size={15} aria-hidden="true" /> Your reviewed version is included in the download.</div></figure>
          <p className="guide-note"><LockKeyhole size={15} aria-hidden="true" /> Only the document owner can export. A teammate can review, and approval may be required first.</p>
        </Tabs.Content>
      </div>
    </Tabs.Root>
    <footer className="guide-footer"><span>Reopen anytime from <strong>Quick guide</strong>.</span><div><button type="button" onClick={() => setTopic(topics[step - 1].id)} disabled={step === 0}><ArrowLeft size={15} aria-hidden="true" /> Back</button><button type="button" className="guide-primary" onClick={() => step === topics.length - 1 ? onDone() : setTopic(topics[step + 1].id)}>{step === topics.length - 1 ? 'Got it' : 'Next'}{step !== topics.length - 1 && <ArrowRight size={15} aria-hidden="true" />}</button></div></footer>
  </>
}
