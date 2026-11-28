// Lane FJ (R3) item 6: PriceNotice.vue and every list that stays quiet when the notice speaks read ONE rule, priceNoticeUp (lib/priceState.js). Review: the component kept its own copy,
// and the copy knew the outcome reply, the page state and the reconnecting flag that priceNoticeUp did not. Spec basis: ADR-330 (56).
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PriceNotice from '@/components/states/PriceNotice.vue'
import { priceNoticeUp } from '@/lib/priceState'

const live = { state: 'LIVE', market_closed: false, last_price_at: '2026-11-27T09:00:00Z' }
const down = { state: 'NOT_CONNECTED', market_closed: false, last_price_at: '2026-11-27T09:00:00Z' }
const closed = { state: 'NOT_CONNECTED', market_closed: true, last_price_at: '2026-11-27T10:00:00Z' }
const reply = (over = {}) => ({ market_closed: false, last_price_at: '2026-11-27T09:00:00Z', ...over })
const cases = []
for (const answer of [null, live, down, closed]) {
  for (const r of [null, reply(), reply({ market_closed: true })]) {
    for (const pageState of ['computed', 'stale', 'loading']) {
      for (const reconnecting of [false, true]) {
        for (const affected of [null, 0, 1, 2]) cases.push({ answer, reply: r, pageState, reconnecting, affected })
      }
    }
  }
}
describe('PriceNotice shows exactly when priceNoticeUp says it speaks', () => {
  it(`all ${cases.length} combinations agree`, () => {
    const wrong = []
    for (const c of cases) {
      const w = mount(PriceNotice, { props: c })
      const shown = w.find('[data-testid="price-notice"]').exists() || w.text().length > 0
      const up = priceNoticeUp(c.answer, c.affected, { reply: c.reply, pageState: c.pageState, reconnecting: c.reconnecting })
      if (shown !== up) wrong.push(JSON.stringify(c))
      w.unmount()
    }
    expect(wrong).toEqual([])
  })
  it('the old two-argument call is unchanged', () => {
    expect(priceNoticeUp(down, null)).toBe(true)
    expect(priceNoticeUp(down, 1)).toBe(false)
    expect(priceNoticeUp(live, null)).toBe(false)
    expect(priceNoticeUp(closed, 1)).toBe(true)
  })
})
