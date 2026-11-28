// ADR-330 (56) round 2 (owner 27 Nov 2026): how many strategies are affected is decided in ONE function (priceScope); the page
// notice shows for 2 or more, the one affected tile carries the line alone for exactly 1. Builder times: a price time is the
// price's, a load time is "Checked at". Expected texts are written here, never read back from the code.
// The PaperStrategies tile tests (two paused: greyed, no line; one paused: only it carries the line) are in
// docs/design/next-batch-2026-11-26/lane-n-for-lanes-v-l.md until Lane U/V take that file.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PriceNotice from '@/components/states/PriceNotice.vue'
import { priceScope, tileNotLive } from '@/lib/priceState'
import { sharedTotal } from '@/lib/tracking'

describe('priceScope: the one "how many are affected" function', () => {
  const rows = [{ id: 1, bad: true }, { id: 2, bad: false }, { id: 3, bad: true }]
  it('none / one / many', () => {
    expect(priceScope(rows, () => false)).toMatchObject({ count: 0, scope: 'none' })
    expect(priceScope(rows.slice(0, 2), (r) => r.bad)).toMatchObject({ count: 1, scope: 'one' })
    expect(priceScope(rows, (r) => r.bad)).toMatchObject({ count: 2, scope: 'many' })
    expect(priceScope(null, () => true)).toMatchObject({ count: 0, scope: 'none' })
  })
  it('tileNotLive: many greys without a line; one greys with the line; an unaffected tile is plain', () => {
    const many = priceScope(rows, (r) => r.bad)
    expect(tileNotLive(many, 1)).toEqual({ greyed: true, line: false })
    expect(tileNotLive(many, 2)).toEqual({ greyed: false, line: false })
    const one = priceScope(rows.slice(0, 2), (r) => r.bad)
    expect(tileNotLive(one, 1)).toEqual({ greyed: true, line: true })
    expect(tileNotLive(one, 2)).toEqual({ greyed: false, line: false })
  })
})

describe('PriceNotice with the affected count', () => {
  const down = { state: 'NOT_CONNECTED', market_closed: false, last_price_at: '2026-11-27T10:28:01Z', indices: [] }
  it('exactly one affected: no page notice; two: the notice; closed: the banner whatever the count', () => {
    expect(mount(PriceNotice, { props: { answer: down, affected: 1 } }).find('[data-testid="price-notice"]').exists()).toBe(false)
    expect(mount(PriceNotice, { props: { answer: down, affected: 2 } }).get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 15:58:01 IST.')
    const closed = mount(PriceNotice, { props: { answer: { ...down, market_closed: true, last_price_at: '2026-11-27T10:00:00Z' }, affected: 1 } })
    expect(closed.get('[data-testid="market-closed-text"]').text()).toBe('Market closed. Prices are from 27 Nov 2026, 15:30:00 IST.')
  })
})

describe('Builder times: a price time is the price time, a load time is "Checked at"', () => {
  it('only an answer time -> "Checked at", never "As of"', () => {
    const book = { total_text: '100.00', answered_at: '2026-11-27T10:43:47Z', state: 'LIVE' }
    expect(sharedTotal(book).line).toBe('Checked at 16:13:47 IST')
  })
  it('a price time from the reply -> "As of" that time', () => {
    const book = { total_text: '100.00', answered_at: '2026-11-27T10:43:47Z', last_price_at: '2026-11-27T10:28:01Z', state: 'LIVE' }
    expect(sharedTotal(book).line).toBe('As of 15:58:01 IST')
  })
})
