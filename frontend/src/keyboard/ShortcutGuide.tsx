import { useId, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { searchShortcuts } from './shortcuts'

const groups: { title: string; keys: string[] }[] = [
  { title: 'Navigation', keys: ['N', 'P', '?'] },
  { title: 'Review decisions', keys: ['L', 'R', 'K', 'U'] },
  { title: 'Replacement options', keys: ['M', 'F', 'D', 'G'] },
]

export function ShortcutGuide() {
  const id = useId()
  const [query, setQuery] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const matches = searchShortcuts(query)
  function clear() { setQuery(''); input.current?.focus() }
  return <div className="keyboard-guide-body">
    <div className="shortcut-search">
      <Search size={16} aria-hidden="true" />
      <label className="sr-only" htmlFor={id}>Search shortcuts</label>
      <input ref={input} id={id} type="search" placeholder="Find a shortcut…" value={query} onChange={event => setQuery(event.target.value)} />
      {query && <button type="button" aria-label="Clear shortcut search" onClick={clear}><X size={15} aria-hidden="true" /></button>}
    </div>
    <div className="shortcut-results" aria-live="polite">
      {groups.map(group => {
        const rows = matches.filter(([key]) => group.keys.includes(key))
        return rows.length ? <section className="shortcut-group" key={group.title} aria-label={group.title}>
          <h3>{group.title}</h3>
          <dl className="keyboard-shortcut-list">{rows.map(([key, name, note]) => <div key={key}>
            <dt><strong>{name}</strong><kbd>{key}</kbd></dt><dd>{note}</dd>
          </div>)}</dl>
        </section> : null
      })}
      {!matches.length && <div className="shortcut-empty"><h3>No shortcuts found</h3><p>Search by an action, a key, or a replacement style.</p><button type="button" onClick={clear}>Show all shortcuts</button></div>}
    </div>
  </div>
}
