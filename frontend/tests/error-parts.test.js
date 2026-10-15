// W-072 / REQ-039 AC-3, REQ-065 AC-2 under ADR-086: ErrorMessage shows all four parts under their labels, also compact.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const parts = {
  what_happened: 'The page or action you asked for is not available here.',
  impact: 'Nothing on this page can be changed until it is available.',
  what_is_blocked: 'This request.',
  next_action: 'Go back to the previous page and choose again.',
}

describe('ErrorMessage', () => {
  for (const compact of [false, true]) {
    it(`${compact ? 'compact' : 'full'}: all four parts, each under its label`, () => {
      const w = mount(ErrorMessage, { props: { parts, compact, prefix: 'x-error' } })
      const text = w.text()
      expect(w.get('[data-testid="x-error-what"]').text()).toBe(parts.what_happened)
      expect(text).toContain(`What this means: ${parts.impact}`)
      expect(text).toContain(`What is blocked: ${parts.what_is_blocked}`)
      expect(text).toContain(`What to do next: ${parts.next_action}`)
    })
  }
  it('the default test ids are unchanged', () => {
    const w = mount(ErrorMessage, { props: { parts } })
    for (const id of ['error-what', 'error-impact', 'error-blocked', 'error-next']) expect(w.find(`[data-testid="${id}"]`).exists()).toBe(true)
  })
})
