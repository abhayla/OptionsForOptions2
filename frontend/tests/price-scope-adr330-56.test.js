// ADR-330 (56) round 2 (owner 27 Nov 2026): how many strategies are affected is decided in ONE function (priceScope); the page
// notice shows for 2 or more, the one affected tile carries the line alone for exactly 1. Builder times: a price time is the
// price's, a load time is "Checked at". Expected texts are written here, never read back from the code.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
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

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: 'BUY', instrument: 'PE', strike: `${22300 + i * 100}.00`, expiry: '2026-11-03',
  quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live',
  price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (id, over = {}) => withPriceTexts({
  strategy_id: id, name: `"S${id}"`, underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null,
  as_of: null, total: '-1894.75', booked: '0.00', unbooked: '-1894.75', legs: [leg(0), leg(1)], ...over,
})
const paused = { state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' }
async function show(items, props = {}) {
  answers['GET /tracking'] = () => Promise.resolve({ data: { strategies: items, answered_at: '2026-10-28T06:00:00Z' } })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { props, global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('Positions Paper tiles (ADR-330 (56))', () => {
  it('two paused strategies: greyed, no sentence of their own, and the list says 2 are affected', async () => {
    const w = await show([item(1, paused), item(2, paused)])
    const groups = w.findAll('[data-testid="paper-group"]')
    expect(groups).toHaveLength(2)
    for (const g of groups) {
      expect(g.find('[data-testid="paper-state"]').exists()).toBe(false)
      expect(g.classes()).toContain('price-greyed')
    }
    expect(w.emitted('summary').at(-1)[0].affected).toBe(2)
  })
  it('one paused among two: only it carries the line, and the list says 1 is affected', async () => {
    const w = await show([item(1, paused), item(2)])
    const [a, b] = w.findAll('[data-testid="paper-group"]')
    expect(a.get('[data-testid="paper-state"]').text()).toContain('Paper P&L paused - prices not live')
    expect(a.classes()).toContain('price-greyed')
    expect(b.find('[data-testid="paper-state"]').exists()).toBe(false)
    expect(b.classes()).not.toContain('price-greyed')
    expect(w.emitted('summary').at(-1)[0].affected).toBe(1)
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
