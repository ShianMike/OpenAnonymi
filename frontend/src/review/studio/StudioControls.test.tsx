import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { StudioSelect } from './StudioControls'

it('preserves an empty placeholder and numeric values with their accessible labels', () => {
  const render = (value: string | number, disabled = false) => renderToStaticMarkup(<StudioSelect id="retention" aria-label="Retention" value={value} disabled={disabled} onValueChange={() => {}}>
    <option value="">Choose retention</option>{[1, 7].map(days => <option key={days} value={days}>{days} days</option>)}
  </StudioSelect>)
  expect(render('')).toContain('Choose retention')
  expect(render(7)).toContain('7 days')
  expect(render('7')).toContain('7 days')
  expect(render(7, true)).toMatch(/<button[^>]*disabled=""/)
  expect(render(7)).toContain('aria-label="Retention"')
})
