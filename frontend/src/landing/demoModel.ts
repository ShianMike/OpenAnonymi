export type DemoAction = 'label' | 'redact' | 'keep'
export type DemoDecisions = Record<string, DemoAction | undefined>
export type DemoDetail = { id: string; text: string; category: string; label: string }
export type DemoPart = string | DemoDetail
export type DemoExample = { id: string; name: string; title: string; parts: DemoPart[] }

export const examples: DemoExample[] = [
  {
    id: 'interview', name: 'Interview', title: 'A little feedback, worth sharing.',
    parts: [
      '“The invitation could be clearer,” said ',
      { id: 'person', text: 'Maya Chen', category: 'Person', label: 'PERSON_001' },
      '.\n\nShe liked the new onboarding flow and offered to try the next version.\n\nFollow up: ',
      { id: 'email', text: 'maya@example.com', category: 'Email', label: 'EMAIL_001' },
      '\nCall: ',
      { id: 'phone', text: '+1 202-555-0142', category: 'Phone', label: 'PHONE_001' },
    ],
  },
  {
    id: 'support', name: 'Support note', title: 'Keep the useful part of the conversation.',
    parts: [
      '🙂 ',
      { id: 'person', text: 'Leon Rivera', category: 'Person', label: 'PERSON_001' },
      ' found a confusing step in the account setup.\n\nThe fix: add a clearer invitation link. That insight belongs in the team recap.\n\nReply to ',
      { id: 'email', text: 'leon@example.com', category: 'Email', label: 'EMAIL_001' },
      ' or call ',
      { id: 'phone', text: '+1 202-555-0186', category: 'Phone', label: 'PHONE_001' },
      '.',
    ],
  },
]

export const actionNames: Record<DemoAction, string> = { label: 'Label', redact: 'Redact', keep: 'Keep' }

export function detailOutput(detail: DemoDetail, action: DemoAction | undefined) {
  if (action === 'label') return detail.label
  if (action === 'redact') return '[REDACTED]'
  return detail.text
}

export function demoOutput(parts: DemoPart[], decisions: DemoDecisions) {
  return parts.map((part) => typeof part === 'string' ? part : detailOutput(part, decisions[part.id])).join('')
}
