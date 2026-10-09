import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkdownText } from './MarkdownText'
import { segmentText, type ReviewFinding } from './textSegments'

function render(text: string, needles: string[] = [], plain = false) {
  const marks = needles.map((needle, index) => {
    const offset = text.indexOf(needle)
    const span = { start: Array.from(text.slice(0, offset)).length, end: Array.from(text.slice(0, offset + needle.length)).length }
    const finding = { finding_id: `finding-${index}`, span } as ReviewFinding
    return { finding, span }
  })
  return renderToStaticMarkup(<MarkdownText text={text} plain={plain} segments={segmentText(text, marks)}
    renderSegment={segment => segment.findings[0] ? <button key={segment.start}
      data-finding={segment.findings[0].finding_id} data-start={segment.start}>{segment.text}</button> : segment.text} />)
}

describe('formatted review Markdown', () => {
  it('renders headings, tables, tasks, quotes and code with original Unicode finding offsets', () => {
    const text = '# Meeting 😀\r\n\r\n> Prepared by **Maya Ellison** (`maya@example.com`)\r\n\r\n'
      + '| Name | Contact |\r\n| --- | --- |\r\n| Daniel | daniel@example.org |\r\n\r\n'
      + '- [ ] Call *Jordan Avery*.\r\n- [x] Done.\r\n\r\n'
      + '```text\r\nuser=jordan@example.net ip=192.0.2.18\r\n```\r\n'
    const needles = ['Maya Ellison', 'maya@example.com', 'daniel@example.org', 'Jordan Avery', 'jordan@example.net', '192.0.2.18']
    const html = render(text, needles)
    expect(html).toContain('<h2>Meeting 😀</h2>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<table>')
    expect(html).toContain('<th scope="col">Contact</th>')
    expect(html).toContain('aria-label="To do task"')
    expect(html).toContain('aria-label="Completed task"')
    expect(html).toContain('<pre><code>user=')
    needles.forEach((needle, index) => {
      const start = Array.from(text.slice(0, text.indexOf(needle))).length
      expect(html).toContain(`data-finding="finding-${index}" data-start="${start}">${needle}</button>`)
    })
    expect(html).not.toContain('```')
  })

  it('keeps HTML, links, images and reference destinations inert and reviewable', () => {
    const text = '# Untrusted\n<script>alert("x")</script>\n\n'
      + '[Contact](https://example.test/private?email=maya@example.com)\n\n'
      + '![image](https://example.test/image.png)\n\n[site][private]\n\n'
      + '[private]: https://example.test/private\n'
    const html = render(text, ['maya@example.com', 'https://example.test/image.png', '[private]:'])
    expect(html).not.toMatch(/<(script|img|a)\b/)
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain('data-finding="finding-0"')
    expect(html).toContain('data-finding="finding-1"')
    expect(html).toContain('data-finding="finding-2"')
    expect(html).toContain('https://example.test/private')
  })

  it('retains findings on syntax, entities and plain-text whitespace', () => {
    expect(render('😀 café\r\n  two spaces')).toBe('😀 café\r\n  two spaces')
    expect(render('# literal CSV cell | **value**', [], true)).toBe('# literal CSV cell | **value**')
    const html = render('# Zo&#235;\n\n**visible**', ['&#235;', '**'])
    expect(html).toContain('&amp;#235;')
    expect(html).toContain('Other marked text')
    expect(html).toContain('data-finding="finding-1"')
  })
})
