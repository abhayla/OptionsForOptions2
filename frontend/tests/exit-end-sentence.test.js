// Lane U hotfix (27 Nov 2026), ADR-016..019, REQ-065: one door, one sentence. Every placed end of an Exit, on Positions and on the
// builder, is "<leg(s)>: Exit placed on paper (order n)." / "(orders n, m)", built only by exitEndText.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { exitEndText } from '@/lib/usePaperExit'

const reply = { orders: [{ id: 960 }, { id: 965 }] }
describe('the placed sentence', () => {
  it('one reply, both pages -> identical text (same builder, same call shape)', () => {
    const positions = exitEndText('done', ['22300 PE'], { orders: reply.orders, sent: 1 }, 'x')
    const builder = exitEndText('done', ['22300 PE'], { orders: reply.orders, sent: 1 })
    expect(builder).toBe(positions)
    expect(positions).toBe('22300 PE: Exit placed on paper (order 965).')
  })
  it('two orders -> "(orders n, m)"', () => {
    expect(exitEndText('done', ['A', 'B'], { orders: reply.orders, sent: 2 })).toBe('A, B: Exit placed on paper (orders 960, 965).')
  })
  it('no ids in hand (a re-read decided it; the paper list carries no order ids) -> no number, never an invented one', () => {
    expect(exitEndText('done', ['A'], {})).toBe('A: Exit placed on paper.')
  })
  it('no second literal: only usePaperExit.js words the placed sentence', () => {
    for (const f of ['src/pages/StrategyBuilderPage.vue', 'src/components/strategy/PaperStrategies.vue']) {
      expect(readFileSync(f, 'utf8').split('\n').filter((l) => !l.trim().startsWith('//') && /Exit placed on paper|EXIT_DONE_TEXT/.test(l))).toEqual([])
    }
  })
})
