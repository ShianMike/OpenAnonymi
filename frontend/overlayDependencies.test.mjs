import { createRequire } from 'node:module'
import { expect, it } from 'vitest'

it('shares dismissal and focus stacks across nested Radix overlays', () => {
  const require = createRequire(import.meta.url)
  const overlays = ['dialog', 'select', 'menu', 'popover']
  for (const shared of ['react-dismissable-layer', 'react-focus-scope']) {
    const modules = overlays.map(name =>
      createRequire(require.resolve(`@radix-ui/react-${name}`)).resolve(`@radix-ui/${shared}`),
    )
    expect(new Set(modules).size, `${shared} must use one shared instance`).toBe(1)
  }
  const command = createRequire(require.resolve('cmdk'))
  expect(command.resolve('@radix-ui/react-dialog')).toBe(require.resolve('@radix-ui/react-dialog'))
})
