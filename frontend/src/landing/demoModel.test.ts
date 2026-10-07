import { describe, expect, it } from 'vitest'
import { demoOutput, examples } from './demoModel'

describe('fictional reviewed output', () => {
  it('preserves the original Unicode text until a decision is made', () => {
    const original = demoOutput(examples[1].parts, {})
    expect(original).toContain('🙂 Leon Rivera')
    expect(original).toContain('leon@example.com')
    expect(original).toContain('flagged a broken invite.')
  })
  it('applies each chosen action without changing the narrative', () => {
    const output = demoOutput(examples[0].parts, { person: 'label', email: 'redact', phone: 'keep' })
    expect(output).toContain('said PERSON_001.')
    expect(output).toContain('Follow up: [REDACTED]')
    expect(output).not.toContain('Maya Chen')
    expect(output).not.toContain('maya@example.com')
    expect(output).toContain('Call: +1 202-555-0142')
    expect(output).toContain('“The invite felt confusing,”')
  })
})
