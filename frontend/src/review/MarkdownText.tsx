import { createElement, Fragment, useMemo, type ReactNode } from 'react'
import { fromMarkdown } from 'mdast-util-from-markdown'
import { gfmFromMarkdown } from 'mdast-util-gfm'
import { gfm } from 'micromark-extension-gfm'
import type { Nodes } from 'mdast'
import type { TextSegment } from './textSegments'

/** Render source positions through the same finding controls as plain text. */
export function MarkdownText({ text, segments, renderSegment, plain = false }: {
  text: string; segments: TextSegment[]; renderSegment: (segment: TextSegment) => ReactNode; plain?: boolean
}) {
  const tree = useMemo(() => {
    if (plain) return null
    try { return fromMarkdown(text, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] }) }
    catch { return null } // Malformed/overly complex input remains reviewable as source text.
  }, [text, plain])
  const formatted = tree?.children.some(node => node.type !== 'paragraph' || node.children.some(child => child.type !== 'text'))
  if (!tree || !formatted) return <>{segments.map(renderSegment)}</>

  const characters = Array.from(text)
  const offsets = new Map<number, number>([[0, 0]])
  let utf16 = 0
  characters.forEach((character, index) => { utf16 += character.length; offsets.set(utf16, index + 1) })
  const visibleFindings = new Set<string>()

  function range(start: number, end: number, value?: string): ReactNode {
    const from = offsets.get(start) ?? 0, to = offsets.get(end) ?? characters.length
    let low = 0, high = segments.length
    while (low < high) {
      const middle = (low + high) >>> 1
      if (segments[middle].end <= from) low = middle + 1
      else high = middle
    }
    const pieces: TextSegment[] = []
    for (let index = low; index < segments.length && segments[index].start < to; index++) {
      const segment = segments[index]
      const start = Math.max(from, segment.start), end = Math.min(to, segment.end)
      pieces.push({ ...segment, start, end, text: characters.slice(start, end).join('') })
      if (segment.findings[0]) visibleFindings.add(segment.findings[0].finding_id)
    }
    // Escapes/entities/code whitespace can display decoded text only when no finding relies on it.
    return value !== undefined && !pieces.some(piece => piece.findings.length)
      ? value : pieces.map(renderSegment)
  }

  function render(node: Nodes, depth = 0): ReactNode {
    const start = node.position?.start.offset ?? 0, end = node.position?.end.offset ?? text.length
    const raw = text.slice(start, end)
    const children = () => 'children' in node ? node.children.map(child =>
      <Fragment key={`${child.type}-${child.position?.start.offset}`}>{render(child, depth + 1)}</Fragment>) : null
    // ponytail: render nesting beyond 100 levels literally to bound recursive rendering.
    if (depth > 100) return range(start, end)
    switch (node.type) {
      case 'root': return children()
      case 'text': return range(start, end, node.value)
      case 'paragraph': return <p>{children()}</p>
      case 'heading': return createElement(`h${Math.min(6, node.depth + 1)}`, null, children())
      case 'strong': return <strong>{children()}</strong>
      case 'emphasis': return <em>{children()}</em>
      case 'delete': return <del>{children()}</del>
      case 'blockquote': return <blockquote>{children()}</blockquote>
      case 'break': return <br />
      case 'thematicBreak': return <hr />
      case 'list': return node.ordered ? <ol start={node.start ?? 1}>{children()}</ol> : <ul>{children()}</ul>
      case 'listItem': return <li className={node.checked === null || node.checked === undefined ? undefined : 'markdown-task'}>
        {typeof node.checked === 'boolean' && <input type="checkbox" checked={node.checked} readOnly disabled
          aria-label={node.checked ? 'Completed task' : 'To do task'} />}{children()}</li>
      case 'inlineCode': {
        const fence = raw.match(/^`+/)?.[0].length ?? 0
        return <code>{range(start + fence, end - fence, node.value)}</code>
      }
      case 'code': {
        const fenced = /^ {0,3}(`{3,}|~{3,})/.test(raw)
        const opening = fenced ? raw.indexOf('\n') + 1 : 0
        const closing = fenced ? raw.match(/\r?\n {0,3}(?:`{3,}|~{3,})[^\n]*$/)?.index : undefined
        return <pre><code>{range(start + opening, start + (closing ?? raw.length), node.value)}</code></pre>
      }
      case 'table': return <div className="markdown-table"><table>
        <thead><tr>{node.children[0].children.map((cell, index) => <th key={index} scope="col"
          style={{ textAlign: node.align?.[index] ?? undefined }}>{render(cell, depth + 1)}</th>)}</tr></thead>
        <tbody>{node.children.slice(1).map((row, index) => <tr key={index}>{row.children.map((cell, column) =>
          <td key={column} style={{ textAlign: node.align?.[column] ?? undefined }}>{render(cell, depth + 1)}</td>)}</tr>)}</tbody>
      </table></div>
      case 'tableCell': return children()
      case 'link': {
        const labelEnd = node.children.at(-1)?.position?.end.offset ?? end
        // Destinations stay visible for review, without requests or navigation.
        return <span className="markdown-link">{children()}{text.slice(labelEnd, labelEnd + 2) === ']('
          && <span className="markdown-destination"> ({range(labelEnd + 2, end - 1)})</span>}</span>
      }
      case 'linkReference': return <span className="markdown-link">{children()}</span>
      // HTML, image destinations, definitions and unsupported syntax remain escaped text.
      default: return range(start, end)
    }
  }

  const content = render(tree)
  const hidden = segments.filter(segment => segment.findings[0] && !visibleFindings.has(segment.findings[0].finding_id))
  return <div className="document-markdown">{content}{hidden.length > 0 && <div className="markdown-extra-findings">
    <h3>Other marked text</h3><p>These details are in Markdown syntax or references.</p>{hidden.map(renderSegment)}
  </div>}</div>
}
