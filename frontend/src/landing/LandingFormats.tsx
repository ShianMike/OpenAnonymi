import { ArrowDownToLine, ArrowUpFromLine, ChevronDown, type LucideIcon } from 'lucide-react'

type Format = { name: string; extensions: string }

const imports: Format[] = [
  { name: 'Text & Markdown', extensions: 'TXT · MD' },
  { name: 'PDF & Word documents', extensions: 'PDF · DOCX' },
  { name: 'Images', extensions: 'PNG · JPEG · TIFF · WebP' },
]
const exports: Format[] = [
  { name: 'Plain text', extensions: 'TXT' },
  { name: 'Word & PDF documents', extensions: 'DOCX · PDF' },
  { name: 'Redaction report', extensions: 'JSON' },
]

function Formats({ title, note, Icon, items }: { title: string; note: string; Icon: LucideIcon; items: Format[] }) {
  return <div className="landing-formats-group">
    <header><h3><Icon size={18} aria-hidden="true" />{title}</h3><span>{note}</span></header>
    <ul aria-label={`${title} formats`}>{items.map(({ name, extensions }) => <li key={name}><span>{name}</span><small>{extensions}</small></li>)}</ul>
  </div>
}

export function LandingFormats() {
  return (
    <section id="file-formats" className="landing-formats" aria-labelledby="formats-title">
      <div className="landing-container" data-landing-reveal>
        <div className="landing-formats-heading">
          <h2 id="formats-title">Your files, ready for review.</h2>
          <p>Start with text, a document, or an image.<br />Choose what to download after you review it.</p>
        </div>
        <div className="landing-formats-inner">
          <Formats title="Import" note="Start with your original" Icon={ArrowUpFromLine} items={imports} />
          <Formats title="Export" note="After you confirm" Icon={ArrowDownToLine} items={exports} />
        </div>
        <details className="landing-format-details">
          <summary>What happens to my document’s layout?<ChevronDown size={16} aria-hidden="true" /></summary>
          <div>
            <p><strong>Text & Markdown</strong>Spaces, tabs, and line breaks are kept. Replacements can change the length of the text.</p>
            <p><strong>Word</strong>Document structure is supported. Editing the extracted text can simplify the layout.</p>
            <p><strong>PDF</strong>Page appearance is kept for PDF imports. The reviewed PDF is image-based; use TXT for selectable text.</p>
          </div>
        </details>
      </div>
    </section>
  )
}
