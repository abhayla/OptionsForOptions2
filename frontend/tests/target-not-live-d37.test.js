// D-37 (seen once, 23 Nov, condor C6): after a level was picked, an answer with no target figures (prices not live) marks the
// target stale; the last block on screen was the plain offer, which carries no stale_text, so Target and Date read "-" with
// no reason. The reply's own sentence (not_live_text) must stand beside each "-". Nothing is computed here (ADR-008).
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TargetBlock from '@/components/strategy/TargetBlock.vue'

const SENTENCE = 'not shown while prices are not live'
const offer = (extra = {}) => ({
  limits: { min: '22800', max: '27900', step: '50', at_min: null, at_max: null },
  move_pct: '0.0', move_pct_display: '0.0%', move_pct_reason: null, days_to_expiry: 5, days_to_expiry_display: '5D to expiry',
  ...extra,
})
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mountStale = (target) => mount(TargetBlock, { props: { target, pick: { level: '25350', dateIndex: 0 }, stopCount: 2, stale: true } })

describe('D-37: the what-if readouts say why they are "-" when prices are not live', () => {
  it('stale with the plain offer (no stale_text): both readouts are "-" and each carries the reply sentence', () => {
    const w = mountStale(offer({ not_live_text: SENTENCE }))
    expect(t(w, 'target-move-text').text()).toBe('-')
    expect(t(w, 'target-days').text()).toContain('-')
    expect(t(w, 'target-move-not-live').text()).toBe(SENTENCE)
    expect(t(w, 'target-days-not-live').text()).toBe(SENTENCE)
  })
  it('the reply without the sentence shows none (nothing is made up here)', () => {
    const w = mountStale(offer())
    expect(t(w, 'target-move-not-live').exists()).toBe(false)
    expect(t(w, 'target-days-not-live').exists()).toBe(false)
  })
  it('not stale: the figures show and no not-live sentence', () => {
    const w = mount(TargetBlock, { props: { target: offer({ not_live_text: SENTENCE }), pick: { level: '', dateIndex: 0 }, stopCount: 2 } })
    expect(t(w, 'target-move-text').text()).toBe('0.0%')
    expect(t(w, 'target-move-not-live').exists()).toBe(false)
  })
})
